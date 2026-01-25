# Install


1. Clone the repo:
   ```sh
   git clone <repo-url>
   ```

2. Sync Python dependencies (from the repo root):
   ```sh
   cd kingdom
   uv sync
   ```

3. Install the `ticket` CLI (and `tk` alias) from the repo root:
   ```sh
   ln -sf "$PWD/ticket" ~/.local/bin/ticket
   ln -sf "$PWD/ticket" ~/.local/bin/tk
   ```
