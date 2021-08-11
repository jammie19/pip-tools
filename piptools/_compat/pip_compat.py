import optparse
import platform
import re
from typing import Iterator, Optional

import pip
from pip._internal.exceptions import InstallationError
from pip._internal.index.package_finder import PackageFinder
from pip._internal.models.link import Link
from pip._internal.network.session import PipSession
from pip._internal.req import InstallRequirement
from pip._internal.req import parse_requirements as _parse_requirements
from pip._internal.req.constructors import install_req_from_parsed_requirement
from pip._internal.req.req_file import ParsedRequirement
from pip._vendor.packaging.version import parse as parse_version

from ..utils import (
    abs_ireq,
    fragment_string,
    install_req_from_link_and_ireq,
    working_dir,
)

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
            try:
                ireq = install_req_from_parsed_requirement(
                    parsed_req, isolated=isolated
                )
            except InstallationError:
                # This can happen when the url is a relpath with a fragment,
                # so we try again with the fragment stripped
                preq_without_fragment = ParsedRequirement(
                    requirement=re.sub(r"#[^#]+=.+$", "", parsed_req.requirement),
                    is_editable=parsed_req.is_editable,
                    comes_from=parsed_req.comes_from,
                    constraint=parsed_req.constraint,
                    options=parsed_req.options,
                    line_source=parsed_req.line_source,
                )
                ireq = install_req_from_parsed_requirement(
                    preq_without_fragment, isolated=isolated
                )

        # At this point the ireq has two problems:
        # - Sometimes the fragment is lost (even without an InstallationError)
        # - It's now absolute (ahead of schedule),
        #   so abs_ireq will not know to apply the _was_relative attribute,
        #   which is needed for the writer to use the relpath.

        # To account for the first:
        if not fragment_string(ireq):
            fragment = Link(parsed_req.requirement)._parsed_url.fragment
            if fragment:
                link_with_fragment = Link(
                    url=f"{ireq.link.url}#{fragment}",
                    comes_from=ireq.link.comes_from,
                    requires_python=ireq.link.requires_python,
                    yanked_reason=ireq.link.yanked_reason,
                    cache_link_parsing=ireq.link.cache_link_parsing,
                )
                ireq = install_req_from_link_and_ireq(link_with_fragment, ireq)

        a_ireq = abs_ireq(ireq, from_dir)

        # To account for the second, we guess if the path was initially relative and
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
