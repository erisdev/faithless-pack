# -------------------------------
import abc
import classtools
import inspect
import os.path
import sys
import time
import traceback

from pathlib import Path

class RuleExecutionError(RuntimeError):
    def __init__(self, rule, ex_type, ex_value, stack):
        self.rule = rule
        self.info = traceback.TracebackException(ex_type, ex_value, stack)

def _filter_params(f, p):
    sig = inspect.signature(f)
    res = {}
    for k, v in p.items():
        if k in sig.parameters:
            res[k] = v
    return res

class Rule(object, metaclass=abc.ABCMeta):
    """abstract base class for makefile rules."""
    def __init__(self, makefile, targets, deps, action):
        self.makefile = makefile
        self.targets = []
        self.deps = []
        self.action = action

        self.targets.extend(targets)
        self.deps.extend(deps)

    def __repr__(self):
        cls = type(self)
        return f"<{cls.__qualname__} {self.targets} : {self.deps}>"

    def depends_on(self, rule):
        """add another rule's targets as dependencies."""
        self.deps.extend(rule.targets)
        return rule

    @property
    @abc.abstractmethod
    def mtime(self):
        """return the modification time of the oldest target."""
        pass

    @abc.abstractmethod
    def should(self):
        """return whether the rule needs to be run."""
        pass

    def execute(self):
        """execute the rule."""
        # TODO makefile paramters too
        sig = inspect.signature(self.action)
        p = {
            'target': self.targets[0],
            'targets': self.targets,
            'dep': self.deps[0] if self.deps else None,
            'deps': self.deps,
        }
        try:
            self.action(**_filter_params(self.action, p))
        except Exception as ex:
            ex_type, ex_value, stack = sys.exc_info()
            raise RuleExecutionError(self, ex_type, ex_value, stack.tb_next)

def _empty():
    pass
_empty = _empty.__code__.co_code

def _empty_with_docstring():
    """dummy"""
_empty_with_docstring = _empty_with_docstring.__code__.co_code

class PhonyRule(Rule):
    """a rule that doesn't touch any files.

    a phony rule is always considered out of date and will always run when it appears in the dependency tree. beware: that means a file rule that depends on a phony rule will always run too.
    """

    @property
    def mtime(self):
        return time.time()

    @classtools.reify
    def trivial(self):
        """return whether this rule is trivial, i.e., its function body is empty."""
        return self.action.__code__.co_code in (_empty, _empty_with_docstring)

    def should(self):
        for dep in map(self.makefile.lookup_rule, self.deps):
            if dep.should():
                return True
        return not self.trivial

def _mtime(filename):
    if os.path.exists(filename):
        return os.path.getmtime(filename)
    else:
        return 0

class FileRule(Rule):
    """a rule that modifies one or more files.

    a file rule is considered out of date if any of its targets are older than the makefile *or* any of the rule's dependencies.
    """

    # @classtools.reify
    @property
    def mtime(self):
        """check the modification time of all targets and return the oldest."""
        return min(map(_mtime, self.targets))

    def should(self):
        if not all(map(os.path.exists, self.targets)):
            return True
        # elif self.makefile.mtime > self.mtime:
        #     return True
        for dep in map(self.makefile.lookup_rule, self.deps):
            if dep.should():
                return True
            elif dep.mtime > self.mtime:
                return True
            else:
                return False

    def execute(self):
        # try:
        #     del self.mtime
        # except AttributeError:
        #     pass
        for t in self.targets:
            os.makedirs(os.path.dirname(t), exist_ok=True)
        super().execute()

class SourceFileRule(FileRule):
    """a rule that represents a single source file.

    a source file is never out of date because it does not depend on any other files.
    """
    def __init__(self, makefile, filename):
        super().__init__(makefile, [filename], [], None)

    @property
    def trivial(self):
        return True

    def should(self):
        return False

    def execute(self):
        pass

class FileMatcher(object):
    def __init__(self, makefile, pattern, exclude, callback):
        self.makefile = makefile
        self.pattern = pattern
        self.callback = callback

        self.exclude = []
        self.exclude.extend(exclude)

    def match(self, filename):
        return filename.match(self.pattern) \
            and not any(filter(filename.match, self.exclude))

    def process_file(self, filename):
        filename = Path(filename)
        if self.match(filename):
            self.callback(filename)

    def process_all(self):
        for filename in Path().glob(self.pattern):
            if self.match(filename):
                self.callback(filename)

# -------------------------------
import functools

def rule(makefile, *targets):
    """create a new rule."""
    targets = list(map(str, filter(None, targets)))
    def decorator(f):
        deps = getattr(f, '__make_deps__', [])
        if targets:
            factory = FileRule
        else:
            factory = PhonyRule
            targets.append(f.__name__)
        rule = factory(makefile, targets, deps, f)
        makefile.add_rule(rule)
        return rule
    return decorator

def deps(makefile, *deps):
    """attach dependencies to the rule."""
    def decorator(f):
        if not hasattr(f, '__make_deps__'):
            f.__make_deps__ = []
        f.__make_deps__.extend(map(str, filter(None, deps)))
        return f
    return decorator

def bind_params(makefile, **params):
    """bind values to the rule's keyword arguments."""
    def decorator(f):
        return functools.partial(f, **params)
    return decorator

def match(makefile, pattern):
    """create a new file matcher"""
    def decorator(f):
        exclude = getattr(f, '__make_exclude__', [])
        matcher = FileMatcher(makefile, pattern, exclude, f)
        makefile.add_matcher(matcher)
        return matcher
    return decorator

def exclude(makefile, *patterns):
    """attach a list of excluded patterns to the file matcher"""
    def decorator(f):
        if not hasattr(f, '__make_exclude__'):
            f.__make_exclude__ = []
        f.__make_exclude__.extend(map(str, filter(None, patterns)))
        return f
    return decorator

# -------------------------------
import functools
import progressbar
import time

from collections import OrderedDict

try:
    from watchdog.observers import Observer
    from watchdog.events import PatternMatchingEventHandler, FileSystemEventHandler
except ModuleNotFoundError:
    have_watchdog = False
else:
    have_watchdog = True

class MakeError(RuntimeError):
    pass

decorators = [rule, deps, bind_params, match, exclude]

class Makefile(object):
    def __init__(self):
        self.mtime = 0
        self.rules = OrderedDict()
        self.matchers = []
        self._injected_locals = {'makefile':self}
        self._injected_locals.update(
            {f.__name__:functools.partial(f, self) for f in decorators})

    def load(self, filename):
        self.mtime = os.path.getmtime(filename)
        with open(filename) as srcfile:
            code = compile(srcfile.read(), filename, 'exec')
        exec(code, {**self._injected_locals})

    def add_rule(self, rule):
        for target in rule.targets:
            self.rules[target] = rule

    def add_matcher(self, matcher):
        self.matchers.append(matcher)
        matcher.process_all()

    def lookup_rule(self, target):
        if target in self.rules:
            return self.rules[target]
        elif target == 'default':
            return self.default_rule()
        elif os.path.exists(target):
            rule = SourceFileRule(self, target)
            self.add_rule(rule)
            return rule
        else:
            raise MakeError(f"no rule to make {target}")

    def default_rule(self):
        # stinky way to get the first item,
        if len(self.rules):
            return next(iter(self.rules.values()))
        else:
            raise MakeError("there are no rules")

    def invoke(self, target='default', watch=False):
        if watch:
            return self._watch(target)
        else:
            queue = self._collect(target)
            return self._invoke_queue(queue)

    def _collect(self, target):
        def collect(target, queue=OrderedDict(), chain=OrderedDict()):
            rule = self.lookup_rule(target)
            if rule in chain:
                raise MakeError("cyclical dependency detected")
            else:
                queue[rule] = True
                queue.move_to_end(rule)
                chain[rule] = True
                for dep in rule.deps:
                    collect(dep, queue, chain)
                chain.popitem(last=True)
            return queue
        return list(reversed(collect(target)))

    def _watch(self, target):
        queue = self._collect(target)
        observer = Observer()

        def on_created(event):
            nonlocal queue
            for matcher in self.matchers:
                matcher.process_file(event.src_path)
            queue = self._collect(target)

        def on_modified(event):
            rule = self.lookup_rule(event.src_path)
            if isinstance(rule, SourceFileRule):
                self._invoke_queue(queue)

        handler = FileSystemEventHandler()
        handler.on_created = on_created
        handler.on_modified = on_modified
        observer.schedule(handler, '.', recursive=True)

        self._invoke_queue(queue)

        observer.start()
        observer.join()
        return True

    def _invoke_queue(self, queue):
        queue = list(filter(lambda rule: rule.should(), queue))
        if not queue:
            return False

        progress = progressbar.ProgressBar(
            redirect_stdout=True,
            max_value=len(queue),
            widgets=[
                progressbar.SimpleProgress("%(value_s)s/%(max_value_s)s"),
                progressbar.Bar(left=" ├", right="┤ ", marker="█", fill="─"),
                progressbar.AdaptiveETA(),
            ])
        with progress:
            for i, rule in enumerate(queue):
                print(f"=> {rule.targets[0]}")
                rule.execute()
                progress.update(i + 1)

        return True

# -------------------------------
import click

class PancakeCommand(click.Group):
    def get_command(self, ctx, name):
        cmd = super().get_command(ctx, name)
        if cmd:
            return cmd
        else:
            @click.command(
                context_settings=dict(
                    ignore_unknown_options=True,
                    allow_extra_args=True))
            def _cmd():
                ctx.invoke(make, target=name)
            return _cmd

@click.group(
    cls=PancakeCommand,
    invoke_without_command=True)
@click.option('-F', 'filename',
    help="file to load rules from",
    default='Makefile.py',
    show_default=True,
    type=click.Path(exists=True))
@click.pass_context
def pancake_cli(ctx, filename):
    makefile = Makefile()
    makefile.load(filename)
    ctx.obj = makefile
    if not ctx.invoked_subcommand:
        ctx.invoke(make)

@pancake_cli.command(
    help="run a task (default)")
@click.option('-w', '--watch',
    help="watch for changes to any files in the dependency tree and automatically re-run when they occur",
    is_flag=True)
@click.argument('target', default='default')
@click.pass_context
def make(ctx, target, watch):
    makefile = ctx.obj
    try:
        made = makefile.invoke(target, watch=watch)
    except MakeError as ex:
        ctx.fail(ex)
    except RuleExecutionError as ex:
        ctx.fail('\n',join([
            f"something went wrong while making {ex.rule.targets[0]}:",
            *ex.info.format()
        ]))
    else:
        if not made:
            click.echo(f"nothing to do for {target}")

@pancake_cli.command(
    help="list rules defined by the build script")
@click.option('-a', 'list_all',
    help="include file rules in the listing",
    is_flag=True)
@click.pass_context
def list_rules(ctx, list_all):
    makefile = ctx.obj
    default = makefile.default_rule()
    for rule in set(makefile.rules.values()):
        if rule == default:
            print(f"{rule.targets[0]} (default)")
        elif list_all or not isinstance(rule, FileRule):
            print(f"{rule.targets[0]}")

if __name__ == '__main__':
    pancake_cli()
