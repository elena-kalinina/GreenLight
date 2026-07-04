"""Scripted human gate for demo runs (auto-approves)."""


class DemoHuman:
    def ask(self, prompt, options=None):
        return options[0] if options else "approve"
