import math,random
import numpy as np
from plm_l1_v09.component.algebra import require

def update(memory,features,reward,gain=0.03):
    require(type(reward) in (int,float) and math.isfinite(reward) and -2<=reward<=2,'bounded_external_utility')
    require(type(gain) in (int,float) and 0<gain<=1,'selector_learning_gain')
    x=memory.encode(features);error=reward-memory.predict(features);energy=float(np.mean(np.sum(np.abs(x)**2,axis=1))/memory.dimension)
    require(energy>0,'empty_selector_signal');new=memory.weights+gain*error*x/energy
    require(np.isfinite(new).all(),'selector_nonfinite_update');memory.weights=new;memory.updates+=1
    return float(error)

def fit(memory,examples,epochs=12):
    require(type(epochs) is int and 1<=epochs<=100,'selector_epochs');loss=[]
    for epoch in range(epochs):
        order=list(range(len(examples)));random.Random('selector-fit-06/'+str(epoch)).shuffle(order);errors=[]
        for i in order:errors.append(update(memory,examples[i]['features'],examples[i]['reward']))
        loss.append(float(np.mean(np.square(errors))))
    return loss
