"""Build an unsigned Windows snapshot from tracked source and the upstream runtime spec."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[2]


def run_git(*args: str) -> str:
    return subprocess.check_output(
        ['git', '-c', f'safe.directory={ROOT.as_posix()}', '-C', str(ROOT), *args],
        text=True,
    ).strip()


def build(output: Path) -> None:
    if sys.platform != 'win32':
        raise SystemExit('The Windows runtime must be built on Windows.')
    output = output.resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    commit = run_git('rev-parse', 'HEAD')
    with tempfile.TemporaryDirectory(prefix='od-fork-', dir=output.parent) as directory:
        work = Path(directory)
        source_zip = work / 'source.zip'
        run_git('archive', '--format=zip', f'--output={source_zip}', commit)
        source = work / 'source'
        with ZipFile(source_zip) as archive:
            source_names = [item.filename for item in archive.infolist() if not item.is_dir()]
            archive.extractall(source)
        base = (source / 'tools/fork/upstream-base.txt').read_text(encoding='utf-8').strip()
        version = f'{base}-fork.{commit[:8]}'
        (source / 'src/one_dragon/version.py').write_text(f'__version__ = {version!r}\n', encoding='utf-8')
        dist = work / 'dist'
        subprocess.run(
            [
                sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                '--distpath', str(dist), '--workpath', str(work / 'build'),
                'OneDragon-RuntimeLauncher.spec',
            ],
            cwd=source / 'deploy',
            check=True,
        )
        runtime = dist / 'OneDragon-RuntimeLauncher'
        executable = runtime / 'OneDragon-RuntimeLauncher.exe'
        if not executable.is_file() or not (runtime / '.runtime').is_dir():
            raise RuntimeError('The embedded runtime or launcher is missing')

        # Build metadata marks a snapshot with a read-only code updater.
        marker = json.dumps({'upstream': base, 'commit': commit, 'version': version}, indent=2) + '\n'
        prefix = 'OneDragon-Fork'
        archive_path = work / 'artifact.zip'
        with ZipFile(archive_path, 'x', compression=ZIP_DEFLATED, compresslevel=5) as archive:
            for name in source_names:
                archive.write(source / name, f'{prefix}/{name}')
            for path in sorted(runtime.rglob('*')):
                if path.is_file():
                    name = path.relative_to(runtime).as_posix()
                    archive.write(path, f'{prefix}/{name}')
            archive.writestr(f'{prefix}/fork-build.json', marker)
        # Test the extracted layout, including the hidden runtime directory.
        extracted = work / 'check'
        with ZipFile(archive_path) as archive:
            archive.extractall(extracted)
        launcher = extracted / prefix / executable.name
        result = subprocess.run([str(launcher), '--version'], check=True, capture_output=True, timeout=60)
        if version.encode() not in result.stdout:
            raise RuntimeError('The bundled launcher did not report the build version')
        archive_path.rename(output)
    print(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output)
