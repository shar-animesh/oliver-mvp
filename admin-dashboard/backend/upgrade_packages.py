"""
https://gist.github.com/yamanahlawat/270a120dd1981010a9336b871f80a39b
Script to automatically update uv.lock and then update pyproject.toml dependencies.

Prerequisites:
    1. Python 3.11+ (for tomllib)
    2. tomli-w package (`pip install tomli-w`)
    3. uv installed and available in PATH

Usage:
    Run this script: `uv run upgrade_packages.py`

    The script will:
    1. Automatically run `uv lock -U` to update the lockfile
    2. Update pyproject.toml based on the new lock file

Notes:
    - Preserves dependency extras and environment markers
    - Updates both main dependencies and dependency groups
    - Removes duplicate version constraints
"""

import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Dict

import tomli_w
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name


def run_uv_lock_update() -> bool:
    """Run uv lock -U command and return success status."""
    print("Running 'uv lock -U' to update dependencies...")
    print("-" * 50)

    try:
        # Run uv lock -U
        result = subprocess.run(["uv", "lock", "-U"], capture_output=True, text=True, check=True)

        # Print output
        if result.stdout:
            print(result.stdout)

        print("-" * 50)
        print("✓ Successfully updated uv.lock")
        return True

    except subprocess.CalledProcessError as e:
        print(f"✗ Error running 'uv lock -U': {e}")
        if e.stderr:
            print(f"Error output: {e.stderr}")
        return False
    except FileNotFoundError:
        print("✗ Error: 'uv' command not found. Please ensure uv is installed and in PATH.")
        return False


def update_requirement(dependency: str, versions: Dict[str, str]) -> str:
    """Update the lower bound while preserving extras, upper bounds, exclusions, and markers."""
    try:
        requirement = Requirement(dependency)
    except InvalidRequirement as error:
        raise ValueError(f"Unsupported dependency requirement: {dependency}") from error
    if requirement.url:
        return dependency
    package_name = canonicalize_name(requirement.name)
    locked_version = versions.get(package_name)
    if locked_version is None:
        return dependency
    preserved = sorted(str(specifier) for specifier in requirement.specifier if specifier.operator != ">=")
    specifiers = ",".join([f">={locked_version}", *preserved])
    extras = f"[{','.join(sorted(requirement.extras))}]" if requirement.extras else ""
    marker = f"; {requirement.marker}" if requirement.marker else ""
    return f"{package_name}{extras}{specifiers}{marker}"


def update_dependencies(pyproject_path: Path, lock_path: Path) -> None:
    """Update pyproject.toml dependencies based on uv.lock."""
    try:
        # Read files
        print("\nReading project files...")
        pyproject = tomllib.loads(pyproject_path.read_text())
        lock_content = lock_path.read_text().split("\n")

        # Parse lock file
        print("\nParsing lock file...")
        versions = {}
        for i, line in enumerate(lock_content):
            if 'name = "' in line:
                name = canonicalize_name(line.split('"')[1])
                if i + 1 < len(lock_content) and 'version = "' in lock_content[i + 1]:
                    versions[name] = lock_content[i + 1].split('"')[1]
        print(f"Found {len(versions)} packages in lock file")

        # Update main dependencies
        print("\nUpdating dependencies...")
        updated_count = 0

        if deps := pyproject.get("project", {}).get("dependencies"):
            print("\nMain dependencies:")
            for i, old_dep in enumerate(deps):
                new_dep = update_requirement(old_dep, versions)
                if old_dep != new_dep:
                    deps[i] = new_dep
                    print(f"  {old_dep} -> {new_dep}")
                    updated_count += 1

        # Update dependency groups
        if groups := pyproject.get("dependency-groups"):
            for group_name, deps in groups.items():
                print(f"\n{group_name} dependencies:")
                for i, old_dep in enumerate(deps):
                    new_dep = update_requirement(old_dep, versions)
                    if old_dep != new_dep:
                        deps[i] = new_dep
                        print(f"  {old_dep} -> {new_dep}")
                        updated_count += 1

        # Write updated pyproject.toml
        if updated_count > 0:
            print(f"\nWriting updated pyproject.toml ({updated_count} dependencies updated)...")
            pyproject_path.write_bytes(tomli_w.dumps(pyproject).encode())
            print("✓ Successfully updated pyproject.toml")
        else:
            print("\n✓ No updates needed - all dependencies are already up to date")

    except Exception as e:
        print(f"\n✗ Error updating dependencies: {e}")
        sys.exit(1)


def main():
    """Main function to coordinate the update process."""
    print("🚀 Starting automated dependency update process...\n")
    current_dir = Path.cwd()
    print(f"Working directory: {current_dir}")

    pyproject_path = current_dir / "pyproject.toml"
    lock_path = current_dir / "uv.lock"

    # Check if required files exist
    if not pyproject_path.exists():
        print("✗ Error: pyproject.toml not found")
        sys.exit(1)
    if not lock_path.exists():
        print("✗ Error: uv.lock not found")
        print("  Run 'uv lock' first to create the lock file")
        sys.exit(1)

    # Step 1: Run uv lock -U
    print("\n" + "=" * 60)
    print("STEP 1: Updating lock file")
    print("=" * 60 + "\n")

    if not run_uv_lock_update():
        print("\n✗ Failed to update lock file. Aborting.")
        sys.exit(1)

    # Step 2: Update pyproject.toml
    print("\n" + "=" * 60)
    print("STEP 2: Updating pyproject.toml")
    print("=" * 60 + "\n")

    update_dependencies(pyproject_path, lock_path)

    print("\n" + "=" * 60)
    print("✓ All done! Your dependencies have been updated.")
    print("=" * 60)


if __name__ == "__main__":
    main()
