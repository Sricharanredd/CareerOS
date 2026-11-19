"""Provider-independent AI adapter layer.

Only this package talks to an external model. Services depend on the
``AnalysisProvider`` protocol, never on a vendor SDK, so the provider can be
swapped or stubbed in tests.
"""
