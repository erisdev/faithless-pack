import os.path

from metapack.candy import fpath

class ModRules(object):
    __forms = (
        ('items',  'dust'),
        ('items',  'nugget'),
        ('items',  'ingot'),
        ('blocks', 'ore'),
        ('blocks', 'block'))

    __src_template = 'assets/common/textures/{kind}/{form}_{metal}'
    __dst_template = 'assets/{namespace}/textures/{kind}/{texture}'

    namespace = None
    metals = None

    @property
    def files(self):
        for kind, form in self.__forms:
            for metal in self.metals:
                src = self._src(kind, form, metal)
                dst = self._dst(kind, form, metal)
                if src and dst:
                    for ext in ('.png', '.png.mcmeta'):
                        yield src + ext, dst + ext

    def _src(self, kind, form, metal):
        return fpath(self.__src_template,
            kind=kind,
            form=form,
            metal=metal)

    def _dst(self, kind, form, metal):
        if hasattr(self, form):
            texture = fpath(getattr(self, form), metal)
            return fpath(self.__dst_template,
                namespace=self.namespace,
                kind=kind,
                texture=texture)
