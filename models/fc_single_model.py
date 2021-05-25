from typing import Any, Dict
import torch
from torch import nn, per_tensor_affine
import pytorch_lightning as pl
from torch.nn.modules.activation import ReLU
from torch.optim.optimizer import Optimizer
import torchmetrics
from typing import Any, Dict, Optional, Type, Union
import models
from models.loss_functions import EVM
from copy import deepcopy


# File with test model FC_cat_regressor
# It's the same model as FC_regressor but it uses doubled sizes of layers
# for real and imaginary part. 
# Input vector is splitted to real and imag parts, these parts are concatenated
# to a single vector, that comes to NN 
# Output is splitted to real and imaginary part, then transformed to complex vector  

class FC_cat_regressor(pl.LightningModule):
    def __init__(
        self, 
        in_features: int,
        layers: int, 
        sizes:list = None, 
        bias = False, 

        optimizer:str = 'Adam',
        optimizer_kwargs: Dict[str, Any] = {'lr':1e-4},
        scheduler: str = 'StepLR',
        scheduler_kwargs: Dict[str, Any] = {'step_size':10},
        criterion: str = 'EVM'
        ):
        '''
        in_features (int) - number of input features in model
        layers (int) - number of layers in model
        sizes (list) - number of output features for each layer. 
            If sizes == None : in_features will be used instead.
        bias (bool) - whether to use bias in linear layers or not.
        
        optimizer (str) - name of optimizer (ex. "Adam", "SGD")
        optimizer_kwargs (dict) - parameters of optimizer (ex. {'lr':1e-4})
        scheduler (str) - name of scheduler that will be used
        scheduler_kwargs (dict) - parameters of scheduler
        criterion (str) - Loss function that will be used for training. "MSE" or "EVM"
        '''
        

        super().__init__()

        self.optimizer = optimizer
        self.optimizer_kwargs = optimizer_kwargs
        self.scheduler = scheduler
        self.scheduler_kwargs = scheduler_kwargs

        self.net = FC_cat_model(in_features, layers, sizes, bias)

        if criterion == 'MSE':
            self.criterion = nn.MSELoss()
        elif criterion == 'EVM':
            self.criterion = EVM()

        self.train_accuracy = torchmetrics.Accuracy()
        self.val_accuracy = torchmetrics.Accuracy()


    def forward(self, x):       
        x = torch.hstack((x.real, x.imag))
        assert len(x)%2 == 0 , 'Wrong concatenation implemetation'
        x = self.net(x)
        half_idxs = len(x)//2
        return x[:half_idxs] + 1j*x[half_idxs:]


    def training_step(self, batch, batch_idx):
        data, target = batch
        preds = self.forward(data)

        loss = self.criterion(preds, target)
        self.log("loss_train", loss, prog_bar = False, logger = True)
        return {"loss":loss, "preds": preds, "target": target}


    def validation_step(self, batch, batch_idx):
        data, target = batch
        preds = self.forward(data)

        return {'preds':preds , 'target': target}


    def configure_optimizers(self):
        OptimizerClass = getattr(torch.optim, self.optimizer)
        SchedulerClass = getattr(torch.optim.lr_scheduler, self.scheduler)
        opt = OptimizerClass(self.parameters(), **self.optimizer_kwargs)
        sch = SchedulerClass(opt, **self.scheduler_kwargs)

        return [opt], [sch]


    def training_epoch_end(self, outputs):
        preds = torch.cat([r['preds'] for r in outputs], dim=0)
        targets = torch.cat([r['target'] for r in outputs], dim=0)
        self.train_accuracy(preds, targets)
        self.log('accuracy_train', self.train_accuracy, prog_bar = True, logger = True)
    

    def validation_epoch_end(self, outputs):
        preds = torch.cat([r['preds'] for r in outputs], dim=0)
        targets = torch.cat([r['target'] for r in outputs], dim=0)

        self.val_accuracy(preds, targets)
        self.log('accuracy_val', self.val_accuracy, prog_bar = True, logger = True)

    def get_configuration(self):
        '''
        Returns dict of str with current configuration of the model.
        Can be used for Logger.
        '''
        configuration = {
            'n_layers': self.net.n_layers, 
            'sizes': self.net.sizes,
            'activation': self.net.activation_name, 
            'criterion': str(self.criterion.__repr__())[:-2],
            'optimizer': self.optimizer,
            'optimizer_param': str(self.optimizer_kwargs)[1:-1], 
            'scheduler': self.scheduler,
            'scheduler_param': str(self.scheduler_kwargs)[1:-1]
        }
        return configuration


class FC_cat_model(torch.nn.Module):
    '''
    Model with linear (fully connected) layers only.
    Number of layers and sizes can be tuned.
    '''
    
    def __init__(self, in_features: int, layers: int, sizes:list = None, bias: bool = False, activation: str = 'ReLU'):
        '''
        @in_features - number of features in input vector
        @layers - number of linear layers in model
        @sizes - list of output features for linear layers. 
            if @sizes == None : uses @in_features for all layers instead
        @bias - whether to use bias for linear layers or not
        '''
        super(FC_cat_model, self).__init__()
        # check if @sizes was defined 
        if sizes != None:
            # check if the @sizes has number of elements equal to number of layers
            if len(sizes) != layers:
                raise Exception('Number of sizes do not match to number of layers. Define sizes for all layers.')
            self.sizes = sizes        
        else:
            # if @sizes == None: use @in_features for all layers
            self.sizes = [in_features for _ in range(layers)]

        # Add input size to the begining of @sizes
        self.sizes.insert(0, in_features)

        # double size for real and imag part
        self.sizes = [size*2 for size in self.sizes]

        # Number of layers and list of layers
        self.n_layers = layers
        self.layers = nn.ModuleList([])

        # Activation function
        ActivationClass = getattr(torch.nn, activation)

        #parameters for saving configuaration
        self.bias = bias
        self.activation_name = activation

        # Adding linear layers and activations to list
        for idx in range(layers):
            self.layers.append(nn.Linear(self.sizes[idx], self.sizes[idx+1], bias = bias))
            self.layers.append(ActivationClass())
        


    def forward(self, x):
        # forward prop for all layers
                 
        for layer in self.layers:
            x = layer(x)

        return x 



