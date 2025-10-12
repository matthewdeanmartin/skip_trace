# safe_targz.py
from __future__ import annotations

import os
import tarfile
from pathlib import Path, PurePosixPath
from posixpath import normpath as posix_normpath
from tarfile import TarFile, TarInfo
from typing import Iterable, List, Tuple


class TarExtractionError(Exception):
    pass


def _is_within(base: Path, target: Path) -> bool:
    try:
        base_resolved = base.resolve(strict=False)
        target_resolved = target.resolve(strict=False)
    except Exception:
        # Fall back if resolve fails on not-yet-created parents
        base_resolved = base.absolute()
        target_resolved = target.absolute()
    try:
        target_resolved.relative_to(base_resolved)
        return True
    except Exception:
        return False


def _sanitize_member_name(name: str) -> str:
    # Tar paths are POSIX; normalize and strip leading "./"
    name = name.lstrip("./")
    name = posix_normpath(name)
    return name


def _is_bad_path(name: str) -> bool:
    # Reject absolute paths, Windows drive letters, parent traversal
    if not name or name == ".":
        return True
    if name.startswith("/") or name.startswith("\\"):
        return True
    if ":" in name.split("/")[0]:  # e.g., "C:..." in archives created on Windows
        return True
    parts = PurePosixPath(name).parts
    return any(p == ".." for p in parts)


def _iter_safe_members(
    tf: TarFile, dest: Path, allow_symlinks: bool
) -> Iterable[Tuple[TarInfo, Path]]:
    for m in tf.getmembers():
        clean = _sanitize_member_name(m.name)
        if _is_bad_path(clean):
            continue
        out_path = dest / Path(*PurePosixPath(clean).parts)
        if not _is_within(dest, out_path):
            continue

        # Directories and regular files are allowed
        if m.isdir():
            yield (m, out_path)
        elif m.isreg():
            yield (m, out_path)
        elif m.issym() or m.islnk():
            if not allow_symlinks:
                continue
            # Only allow relative symlink targets that stay inside dest
            link = m.linkname or ""
            link = _sanitize_member_name(link)
            if _is_bad_path(link):
                continue
            # Compute where the symlink would point to
            # (symlink is created relative to out_path.parent)
            target = out_path.parent / Path(*PurePosixPath(link).parts)
            if not _is_within(dest, target):
                continue
            yield (m, out_path)
        else:
            # Block devices, fifos, sockets, etc.
            continue


def _extract_member(tf: TarFile, m: TarInfo, out_path: Path) -> None:
    if m.isdir():
        out_path.mkdir(parents=True, exist_ok=True)
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)

    if m.isreg():
        src = tf.extractfile(m)
        if src is None:
            raise TarExtractionError(f"Missing file data for {m.name!r}")
        with src, open(out_path, "wb") as f:
            # Stream copy without trusting metadata
            for chunk in iter(lambda: src.read(1024 * 1024), b""):
                f.write(chunk)
        # Apply conservative mode for regular files (rw-r--r--)
        try:
            os.chmod(out_path, 0o644)
        except Exception:
            pass  # nosec # noqa
        return

    if m.issym() or m.islnk():
        # Create a symlink with relative target; errors are non-fatal
        try:
            if out_path.exists() or out_path.is_symlink():
                out_path.unlink()
            os.symlink(m.linkname, out_path)
        except Exception:
            # If symlink creation is not permitted (e.g., Windows), skip
            pass  # nosec # noqa
        return


def safe_extract_tar(
    archive: Path, dest: Path, allow_symlinks: bool = False
) -> List[Path]:
    """
    Safely extract a tar archive into 'dest'.
    - Rejects absolute/parent-traversal paths and special members by default.
    - Never calls TarFile.extractall() (satisfies Bandit B202).
    - Returns list of extracted filesystem paths.
    """
    archive = Path(archive)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)

    mode = "r"
    if archive.suffixes[-2:] in [[".tar", ".gz"]] or archive.suffix == ".tgz":
        mode = "r:gz"
    elif archive.suffixes[-2:] == [".tar", ".bz2"]:
        mode = "r:bz2"
    elif archive.suffixes[-2:] == [".tar", ".xz"]:
        mode = "r:xz"
    elif archive.suffix == ".tar":
        mode = "r:*"  # auto-detect compression
    else:
        raise TarExtractionError(f"Unsupported tar archive: {archive.name}")

    extracted: List[Path] = []
    with tarfile.open(archive, mode) as tf:  # type: ignore[call-overload]
        for m, out_path in _iter_safe_members(tf, dest, allow_symlinks=allow_symlinks):
            _extract_member(tf, m, out_path)
            extracted.append(out_path)
    return extracted


def safe_extract_auto(
    download_path: str, extract_dir: str, allow_symlinks: bool = False
) -> List[Path]:
    """
    Backwards-compatible replacement for:
        tarfile.open(...).extractall(extract_dir)
    """
    return safe_extract_tar(
        Path(download_path), Path(extract_dir), allow_symlinks=allow_symlinks
    )
