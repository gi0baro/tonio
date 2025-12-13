import inspect


def is_asyncg(g):
    return inspect.isasyncgen(g) or inspect.iscoroutine(g)
