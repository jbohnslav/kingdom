# Third-party submodules

This folder is reserved for git submodules (vendored third-party code we want to
pin to a specific commit).

## Add a submodule

Recommended:

```bash
uv run scripts/add_submodule.py <name> <url> --branch <branch>
```

Directly with git:

```bash
git submodule add -b <branch> <url> third-party/<name>
```

After adding a submodule, commit both the new submodule entry and `.gitmodules`,
and commit the resulting `.gitmodules` changes.

## Clone and initialize submodules

Fresh clone:

```bash
git clone --recurse-submodules <repo>
```

Existing clone:

```bash
git submodule update --init --recursive
```
