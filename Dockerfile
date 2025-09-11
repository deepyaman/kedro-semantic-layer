# Install uv
FROM ghcr.io/charmbracelet/vhs
COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /uvx /bin/

# Install git
RUN apt-get install -y git

# Change the working directory to the `app` directory
WORKDIR /app

# Copy the project into the image
ADD . /app

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

# Sync the project
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

# Activate the project virtual environment
ENV PATH="/app/.venv/bin:$PATH"

# Change the working directory back to the `vhs` directory
WORKDIR ../vhs
