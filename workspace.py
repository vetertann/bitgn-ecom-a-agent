import json
import shlex

from bitgn.vm.ecom.ecom_connect import EcomRuntimeClientSync
from bitgn.vm.ecom.ecom_pb2 import (
    AnswerRequest,
    DeleteRequest,
    ExecRequest,
    FindRequest,
    ListRequest,
    NodeKind,
    Outcome,
    ReadRequest,
    SearchRequest,
    StatRequest,
    TreeRequest,
    WriteRequest,
)
from google.protobuf.json_format import MessageToDict


OUTCOME_BY_NAME = {
    "OUTCOME_OK": Outcome.OUTCOME_OK,
    "OUTCOME_DENIED_SECURITY": Outcome.OUTCOME_DENIED_SECURITY,
    "OUTCOME_NONE_CLARIFICATION": Outcome.OUTCOME_NONE_CLARIFICATION,
    "OUTCOME_NONE_UNSUPPORTED": Outcome.OUTCOME_NONE_UNSUPPORTED,
    "OUTCOME_ERR_INTERNAL": Outcome.OUTCOME_ERR_INTERNAL,
}


def _format_tree_entry(entry, prefix: str = "", is_last: bool = True) -> list[str]:
    branch = "`-- " if is_last else "|-- "
    lines = [f"{prefix}{branch}{entry.name}"]
    child_prefix = f"{prefix}{'    ' if is_last else '|   '}"
    children = list(entry.children)
    for idx, child in enumerate(children):
        lines.extend(
            _format_tree_entry(
                child,
                prefix=child_prefix,
                is_last=idx == len(children) - 1,
            )
        )
    return lines


def _render_command(command: str, body: str) -> str:
    return f"{command}\n{body}"


def _is_truncated(result) -> bool:
    if getattr(result, "truncated", False):
        return True
    return "warning: result truncated" in getattr(result, "stderr", "").lower()


def _mark_truncated(result, body: str, hint: str) -> str:
    if not _is_truncated(result):
        return body
    marker = f"[TRUNCATED: {hint}]"
    if not body:
        return marker
    return f"{body}\n{marker}"


def _write_request(path: str, content: str) -> WriteRequest:
    kwargs = {
        "path": path,
        "content": content,
    }
    if "content_type" in WriteRequest.DESCRIPTOR.fields_by_name:
        kwargs["content_type"] = content
    return WriteRequest(**kwargs)


def _normalize_args(args: list[str] | str | None) -> list[str]:
    if args is None:
        return []
    if isinstance(args, str):
        return [args]
    return list(args)


class Workspace:
    def __init__(self, harness_url: str):
        self.vm = EcomRuntimeClientSync(harness_url)
        self.submitted = False
        self.answer_payload: dict | None = None

    def tree(self, root: str = "/", level: int = 2) -> str:
        result = self.vm.tree(TreeRequest(root=root, level=level))
        root_entry = result.root
        if not root_entry.name:
            body = "."
        else:
            lines = [root_entry.name]
            children = list(root_entry.children)
            for idx, child in enumerate(children):
                lines.extend(_format_tree_entry(child, is_last=idx == len(children) - 1))
            body = "\n".join(lines)
        body = _mark_truncated(
            result,
            body,
            "tree output hit a limit; use a narrower root or search for a specific term",
        )
        root_arg = root or "/"
        level_arg = f" -L {level}" if level > 0 else ""
        return _render_command(f"tree{level_arg} {root_arg}", body)

    def list(self, path: str = "/") -> list[str]:
        result = self.vm.list(ListRequest(path=path))
        return [
            f"{entry.name}/" if entry.kind == NodeKind.NODE_KIND_DIR else entry.name
            for entry in result.entries
        ]

    def read(
        self,
        path: str,
        number: bool = False,
        start_line: int = 0,
        end_line: int = 0,
    ) -> str:
        result = self.vm.read(
            ReadRequest(
                path=path,
                number=number,
                start_line=start_line,
                end_line=end_line,
            )
        )
        return _mark_truncated(
            result,
            result.content,
            "file output hit a limit; use start_line/end_line to read a smaller range",
        )

    def search(self, pattern: str, root: str = "/", limit: int = 10) -> list[dict]:
        limit = max(1, min(int(limit), 20))
        result = self.vm.search(SearchRequest(root=root, pattern=pattern, limit=limit))
        return [
            {"path": match.path, "line": match.line, "text": match.line_text}
            for match in result.matches
        ]

    def find(self, name: str, root: str = "/", kind: str = "all", limit: int = 10) -> list[dict]:
        limit = max(1, min(int(limit), 20))
        kind_value = {
            "all": NodeKind.NODE_KIND_UNSPECIFIED,
            "files": NodeKind.NODE_KIND_FILE,
            "dirs": NodeKind.NODE_KIND_DIR,
        }[kind]
        result = self.vm.find(FindRequest(root=root, name=name, kind=kind_value, limit=limit))
        return MessageToDict(result).get("entries", [])

    def search_text(self, pattern: str, root: str = "/", limit: int = 10) -> str:
        matches = self.search(pattern=pattern, root=root, limit=limit)
        body = "\n".join(f"{m['path']}:{m['line']}:{m['text']}" for m in matches)
        return _render_command(
            f"rg -n --no-heading -e {shlex.quote(pattern)} {shlex.quote(root or '/')}",
            body,
        )

    def write(self, path: str, content: str) -> None:
        self.vm.write(_write_request(path=path, content=content))

    def delete(self, path: str) -> None:
        self.vm.delete(DeleteRequest(path=path))

    def stat(self, path: str) -> dict:
        return MessageToDict(self.vm.stat(StatRequest(path=path)))

    def exec(self, path: str, args: list[str] | str | None = None, stdin: str = "") -> str:
        normalized_args = _normalize_args(args)
        result = self.vm.exec(ExecRequest(path=path, args=normalized_args, stdin=stdin))
        command = " ".join([shlex.quote(path), *(shlex.quote(arg) for arg in normalized_args)]).strip()
        if stdin:
            label = "SQL" if path == "/bin/sql" else "STDIN"
            command = f"{command} <<'{label}'\n{stdin.rstrip()}\n{label}"

        body_parts = []
        if result.stdout:
            body_parts.append(result.stdout.rstrip())
        if result.stderr:
            body_parts.append(f"stderr:\n{result.stderr.rstrip()}")
        if getattr(result, "exit_code", 0):
            body_parts.append(f"[exit {result.exit_code}]")
        body = "\n".join(body_parts) if body_parts else "."
        body = _mark_truncated(
            result,
            body,
            "exec output hit a limit; narrow the SQL query or add LIMIT/WHERE",
        )
        return _render_command(command, body)

    def answer(self, message: str, outcome: str, refs: list[str] | None = None) -> None:
        if self.submitted:
            raise RuntimeError("answer() was already called")
        refs = refs or []
        self.vm.answer(
            AnswerRequest(
                message=message,
                outcome=OUTCOME_BY_NAME[outcome],
                refs=refs,
            )
        )
        self.submitted = True
        self.answer_payload = {
            "message": message,
            "outcome": outcome,
            "refs": refs,
        }


class ExecutionWorkspace:
    """Workspace view exposed to model-written code."""

    def __init__(self, workspace: Workspace):
        self._workspace = workspace

    def tree(self, root: str = "/", level: int = 2) -> str:
        return self._workspace.tree(root=root, level=level)

    def list(self, path: str = "/") -> list[str]:
        return self._workspace.list(path=path)

    def read(
        self,
        path: str,
        number: bool = False,
        start_line: int = 0,
        end_line: int = 0,
    ) -> str:
        return self._workspace.read(
            path=path,
            number=number,
            start_line=start_line,
            end_line=end_line,
        )

    def search(self, pattern: str, root: str = "/", limit: int = 10) -> list[dict]:
        return self._workspace.search(pattern=pattern, root=root, limit=limit)

    def find(self, name: str, root: str = "/", kind: str = "all", limit: int = 10) -> list[dict]:
        return self._workspace.find(name=name, root=root, kind=kind, limit=limit)

    def search_text(self, pattern: str, root: str = "/", limit: int = 10) -> str:
        return self._workspace.search_text(pattern=pattern, root=root, limit=limit)

    def write(self, path: str, content: str) -> None:
        self._workspace.write(path=path, content=content)

    def delete(self, path: str) -> None:
        self._workspace.delete(path=path)

    def stat(self, path: str) -> dict:
        return self._workspace.stat(path=path)

    def exec(self, path: str, args: list[str] | str | None = None, stdin: str = "") -> str:
        return self._workspace.exec(path=path, args=args, stdin=stdin)
