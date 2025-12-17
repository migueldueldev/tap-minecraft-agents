from BaseAgent import BaseAgent

class MinerBot(BaseAgent):
    def __init__(self, mc, workspace):
        super().__init__(mc, workspace)
        self.mc = mc
        self.workspace = workspace

    def perceive(self, **kwargs):
        pass

    def decide(self, **kwargs):
        pass

    def act(self, **kwargs):
        pass