"""Relearn single-event components from pairs; two-event binding is not learned."""
from plm_l1_v06.training import fit as fit_component
from .runtime import EventModel


def fit(pairs,lexicon,*,component_seed="banked-evaluation-0",event_seed="events-development-0",dimension=8192,mode="bound",learning=True):
    component=fit_component(pairs,lexicon,seed=component_seed,dimension=8192,learning=learning)
    return EventModel(component,dimension=dimension,seed=event_seed,mode=mode)
