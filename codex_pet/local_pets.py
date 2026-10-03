"""Validate and install immutable, local-only data packs without selecting them."""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import shutil
import tempfile

from . import pets
from .pet_pack import compile_pack


def import_local_pack(source: Path) -> pets.PetAppearance:
    source = source.resolve()
    compiled = compile_pack(source / 'pet.json', validate_images=True)
    if not pets.valid_local_id(compiled.id) or compiled.id in pets.APPEARANCE_BY_ID:
        raise ValueError('Local pack needs a unique lowercase id; bundled pets cannot be replaced')
    data = json.loads((source / 'pet.json').read_bytes())
    name, description = data.get('display_name', compiled.id), data.get('description', '')
    if (not isinstance(name, str) or not name or len(name) > 80
            or not isinstance(description, str) or len(description) > 500
            or any(ord(c) < 32 for c in name + description)):
        raise ValueError('Invalid display_name or description')
    root = pets.local_pets_dir()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination, index = root / compiled.id, root / 'catalog.json'
    with (root / 'import.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f'Local pet already exists: {compiled.id}; use a new id for a revision')
        records = json.loads(index.read_bytes()) if index.exists() else {}
        if not isinstance(records, dict):
            raise ValueError('Invalid local catalog')
        records[compiled.id] = {'name': name, 'description': description}
        encoded = (json.dumps(records, ensure_ascii=False, indent=2) + '\n').encode()
        if len(encoded) > 65536:
            raise ValueError('Local catalog exceeds byte budget')
        # Only referenced art and known provenance files enter the private copy.
        filenames = {'pet.json'}
        for frame in data['frames'].values():
            if 'file' in frame:
                filenames.add(frame['file'])
        filenames.update(n for n in ('CREDITS.md', 'LICENSE.txt', 'LICENSE.md', 'import-record.json')
                         if (source / n).is_file())
        temporary_index = None
        published = False
        try:
            with tempfile.TemporaryDirectory(prefix='.import-', dir=root) as staging:
                staged = Path(staging)
                for name_in_pack in filenames:
                    original = source / name_in_pack
                    if not original.resolve().is_relative_to(source):
                        raise ValueError('Pack file escapes source directory')
                    target = staged / name_in_pack
                    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    shutil.copyfile(original, target)
                    target.chmod(0o600)
                compile_pack(staged / 'pet.json', validate_images=True)
                with tempfile.NamedTemporaryFile(prefix='.catalog-', dir=root, delete=False) as file:
                    temporary_index = Path(file.name)
                    file.write(encoded)
                    file.flush()
                    os.fsync(file.fileno())
                os.rename(staged, destination)
                published = True
                os.replace(temporary_index, index)
        except BaseException:
            if published:
                shutil.rmtree(destination)
            raise
        finally:
            if temporary_index is not None:
                temporary_index.unlink(missing_ok=True)
    return pets.PetAppearance(compiled.id, name, description)
