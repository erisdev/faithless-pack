import datetime
import json
import mistune
import os
import os.path
import shutil

from pathlib import Path
from subprocess import check_output
from zipfile import ZipFile

from metapack.candy import singleton
from metapack.glitchtex import glitch
from metapack.mods import ModRules

PACK_INFO = {
    'name': "FAITHLESS",
    'version': "0.2.0",
    'description': "it's not faithful, but who cares?",

    'pack_format': 2,
    'date': datetime.date.today().isoformat(),
}

ASEPRITE = os.environ.get('ASEPRITE', 'aseprite')

BUILD_DIR = Path('build')
WOOD_TYPES = ['oak', 'birch', 'spruce']
MODS = []

@MODS.append
@singleton
class embers(ModRules):
    namespace = 'embers'
    metals = ['bronze', 'copper', 'lead', 'silver']

    ore   = 'ore{!C}'
    ingot = 'ingot{!C}'
    block = 'block{!C}'

@MODS.append
@singleton
class immersive_engineering(ModRules):
    namespace = 'immersiveengineering'
    metals = [
        'aluminum', 'constantan',   'copper',
        'electrum', 'lead',         'nickel',
        'silver',   'steel',        'uranium']

    ore   = 'ore_{!L}'
    ingot = 'metal_ingot{!C}'
    block = 'storage_{!L}'

@MODS.append
@singleton
class mekanism(ModRules):
    namespace = 'mekanism'
    metals = ['bronze', 'copper', 'osmium', 'silver', 'steel', 'tin']

    ore    = '{!C}Ore'
    ingot  = '{!C}Ingot'
    block  = '{!C}Block'

# @mods.append
# @singleton
# class tconstruct(ModRules):
#     namespace = 'tconstruct'
#     metals = ['alubrass']
#
#     ore    = 'blocks/ore_{!L}'
#     # nugget = 'items/materials/nugget_{!L}'
#     ingot  = 'items/materials/ingot_{!L}'
#     block  = 'blocks/block_{!L}'

# @metapack.task()
# def show_missing(mod=None):
#     def checklist(filename):
#         with open(filename, 'r') as checklist:
#             for item in filter(Path.exists, map(str.strip, checklist)):
#                 print(item)
#
#     if mod:
#         checklist(f'checklist/{mod}.txt')
#     else:
#         for filename in Path('checklist').glob('*.txt'):
#             checklist(filename)

@rule()
@deps('generate_models', 'export_textures', 'bedrock', 'copy_files', 'build/pack.mcmeta')
def build():
    pass

@rule()
@deps('build', 'pack.png', 'README.md')
def package():
    pack_filename = '{name}-{version}.zip'.format(**PACK_INFO)
    with ZipFile(pack_filename, 'w') as z:
        z.write('build/pack.mcmeta', 'pack.mcmeta')
        z.write('pack.png')

        with open('README.md') as f:
            html = mistune.markdown(f.read())
            z.writestr('README.html', html)

        z.write('build/assets', 'assets')
        for src in Path('build/assets').rglob('*'):
            dst = src.relative_to('build')
            z.write(src, dst)

@rule()
def whats_missing():
    for line in open('checklist/minecraft.txt'):
        texture = Path(line.strip())
        if not (texture.with_suffix('.png').exists() or
                texture.with_suffix('.ase').exists()):
            print(texture)


@rule('build/pack.mcmeta')
def generate_pack_mcmeta(target):
    with open(target, 'w') as f:
        json.dump({ 'pack': PACK_INFO }, f)

@rule()
def export_textures():
    pass

def aseprite_to_mcmeta(anim, mcmeta):
    opts = anim['meta']['layers'][0].get('data')
    if opts:
        opts = opts.split()
    else:
        opts = []

    if len(anim['frames']) > 1:
        frames = []
        for i, frame in enumerate(anim['frames']):
            frames.append({
                'index': i,
                'time': frame['duration'] // 50,
            })
        mcmeta['animation'] = {
            'interpolate': ('interpolate' in opts),
            'frames': frames,
        }

def _if_exists(filename):
    if os.path.exists(filename):
        return filename
    else:
        return None

@match('assets/*/textures/**/*.ase')
def texture_matcher(src):
    @export_textures.depends_on
    @rule(BUILD_DIR/src.with_suffix('.png'),
        BUILD_DIR/src.with_suffix('.png.mcmeta'))
    @deps(src, *filter(os.path.exists, [src.with_suffix('.ase.json')]))
    def aseprite_export_rule(targets, deps):
        output = check_output([ASEPRITE, '-b', deps[0],
            '--sheet', targets[0],
            # '--data', dst + '.json',
            '--sheet-type', 'columns',
            '--format', 'json-array',
            '--list-tags',
            '--list-layers',
            '--list-slices'])

        if len(deps) > 1 and os.path.exists(deps[1]):
            with open(deps[1]) as f:
                mcmeta = json.load(f)
        else:
            mcmeta = {}
        aseprite_to_mcmeta(json.loads(output), mcmeta)
        with open(targets[1], 'w') as f:
            json.dump(mcmeta, f)

@rule()
@deps('export_textures')
def bedrock():
    pass
    # texture_path = BUILD_DIR/'assets/minecraft/textures/blocks'
    # os.makedirs(texture_path/'bedrock', exist_ok=True)
    # for idx in range(16):
    #     filename = texture_path / f'bedrock/{idx:02x}.png'
    #     glitch(filename, list(filter(lambda p: p.endswith('.png'), export_textures.deps)))

def make_bedrock_rules():
    texture_path = BUILD_DIR/'assets/minecraft/textures/blocks'
    def make_bedrock_texture_rule(idx):
        @bedrock.depends_on
        @rule(texture_path / f'bedrock/{idx:02x}.png')
        def bedrock_rule(target):
            tile_list = list(filter(
                lambda p: p.endswith('.png'),
                export_textures.deps))
            glitch(target, tile_list)

    for idx in range(16):
        make_bedrock_texture_rule(idx)
make_bedrock_rules()

@rule()
def copy_files():
    pass

@match('assets/**/*')
@exclude('.DS_Store', '*.ase', '*.ase.json')
def file_matcher(src):
    if src.is_file():
        @copy_files.depends_on
        @rule(BUILD_DIR/src)
        @deps(src)
        def copy_this_file(target, dep):
            shutil.copyfile(dep, target)

for mod in MODS:
    for src, dst in mod.files:
        src = str(BUILD_DIR/src)
        dst = str(BUILD_DIR/dst)
        if src in makefile.rules:
            @copy_files.depends_on
            @rule(dst)
            @deps(src)
            def copy_this_file(target, dep):
                shutil.copyfile(dep, target)

@rule()
def generate_models():
    pass

for material in ('birch', 'oak', 'spruce'):
    base = BUILD_DIR/'assets/minecraft/models/block'

    @generate_models.depends_on
    @rule(base/f'{material}_planks.json')
    @bind_params(material=material)
    def planks_rule(target, material):
        with open(target, 'w') as f:
            f.write(json.dumps({
                'parent': 'block/cube_column',
                'textures': {
                    'side': f'blocks/planks_{material}',
                    'end': f'blocks/{material}/top'
                }
            }))

    @generate_models.depends_on
    @rule(base/f'{material}_outer_stairs.json')
    @bind_params(material=material)
    def outer_stairs_rule(target, material):
        with open(target, 'w') as f:
            f.write(json.dumps({
                'parent': 'block/outer_stairs',
                'textures': {
                    'bottom': f'blocks/{material}/top',
                    'top': f'blocks/{material}/top',
                    'side': f'blocks/{material}/stair_side'
                }
            }))

    @generate_models.depends_on
    @rule(base/f'{material}_inner_stairs.json')
    @bind_params(material=material)
    def inner_stairs_rule(target, material):
        with open(target, 'w') as f:
            f.write(json.dumps({
                'parent': 'block/inner_stairs',
                'textures': {
                    'bottom': f'blocks/{material}/top',
                    'top': f'blocks/{material}/top',
                    'side': f'blocks/{material}/stair_side'
                }
            }))

    @generate_models.depends_on
    @rule(base/f'{material}_stairs.json')
    @bind_params(material=material)
    def stairs_rule(target, material):
        with open(target, 'w') as f:
            f.write(json.dumps({
                'parent': 'block/stairs',
                'textures': {
                    'bottom': f'blocks/{material}/top',
                    'top': f'blocks/{material}/top',
                    'side': f'blocks/{material}/stair_side'
                }
            }))

    @generate_models.depends_on
    @rule(base/f'half_slab_{material}.json')
    @bind_params(material=material)
    def lower_slab_rule(target, material):
        with open(target, 'w') as f:
            f.write(json.dumps({
                'parent': 'block/half_slab',
                'textures': {
                    'bottom': f'blocks/{material}/top',
                    'top': f'blocks/{material}/top',
                    'side': f'blocks/{material}/slab_side'
                }
            }))

    @generate_models.depends_on
    @rule(base/f'upper_slab_{material}.json')
    @bind_params(material=material)
    def upper_slab_rule(target, material):
        with open(target, 'w') as f:
            f.write(json.dumps({
                'parent': 'block/upper_slab',
                'textures': {
                    'bottom': f'blocks/{material}/top',
                    'top': f'blocks/{material}/top',
                    'side': f'blocks/{material}/slab_side'
                }
            }))
