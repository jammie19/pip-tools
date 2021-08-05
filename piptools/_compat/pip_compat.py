import optparse
import platform
import re
from typing import Iterator, Optional

import pip
from pip._internal.index.package_finder import PackageFinder
from pip._internal.network.session import PipSession
from pip._internal.req import InstallRequirement
from pip._internal.req import parse_requirements as _parse_requirements
from pip._internal.req.constructors import install_req_from_parsed_requirement
from pip._vendor.packaging.version import parse as parse_version

from ..utils import abs_ireq, working_dir

PIP_VERSION = tuple(map(int, parse_version(pip.__version__).base_version.split(".")))

file_url_schemes_re = re.compile(r"^((git|hg|svn|bzr)\+)?file:")


def parse_requirements(
    filename: str,
    session: PipSession,
    finder: Optional[PackageFinder] = None,
    options: Optional[optparse.Values] = None,
    constraint: bool = False,
    isolated: bool = False,
    from_dir: Optional[str] = None,
) -> Iterator[InstallRequirement]:
    for parsed_req in _parse_requirements(
        filename, session, finder=finder, options=options, constraint=constraint
    ):
        # This context manager helps pip locate relative paths specified
        # with non-URI (non file:) syntax, e.g. '-e ..'
        with working_dir(from_dir):
            ireq = install_req_from_parsed_requirement(parsed_req, isolated=isolated)

        # But the resulting ireq is absolute (ahead of schedule),
        # so abs_ireq will not apply the _was_relative attribute,
        # which is needed for the writer to use the relpath.
        a_ireq = abs_ireq(ireq, from_dir)

        # To account for that, we guess if the path was initially relative and
        # set _was_relative ourselves:
        bare_path = file_url_schemes_re.sub("", parsed_req.requirement)
        is_win = platform.system() == "Windows"
        if is_win:
            bare_path = bare_path.lstrip("/")
        if (
            a_ireq.link is not None
            and a_ireq.link.scheme.endswith("file")
            and not bare_path.startswith("/")
        ):
            if not (is_win and re.match(r"[a-zA-Z]:", bare_path)):
                a_ireq._was_relative = True

        yield a_ireq
