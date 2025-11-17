from abc import abstractmethod

class BaseAgent:
    def __init__(self):
        pass

    @abstractmethod
    def perceive(self):
        pass

    @abstractmethod
    def decide(self):
        pass
    
    @abstractmethod
    def act(self):
        pass