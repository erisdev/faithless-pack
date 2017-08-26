import os.path

from string import Formatter

class ConvertingFormatter(Formatter):
    def __init__(self, **conversions):
        self.__conversions = conversions

    def convert_field(self, value, conversion):
        if conversion in self.__conversions:
            return self.__conversions[conversion](value)
        else:
            return super().convert_field(value, conversion)

def singleton(cls):
    return cls()

path_formatter = ConvertingFormatter(
    C=str.capitalize,
    L=str.lower,
    U=str.upper,
    d=os.path.dirname,
    b=os.path.basename,
    e=lambda p: os.path.splitext(p)[1],
    E=lambda p: os.path.splitext(p)[0])
def fpath(fmt, *args, **kwargs):
    return path_formatter.format(fmt, *args, **kwargs)
