FROM python:3.14.7
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
RUN useradd --system --uid 10001 --user-group --no-create-home --shell /usr/sbin/nologin rbb
WORKDIR /app
COPY pyproject.toml poetry.lock ./
# Poetry 1.8.5 generated poetry.lock; a different version may re-resolve it.
RUN pip install --no-cache-dir poetry==1.8.5 \
    && poetry config virtualenvs.create false \
    && poetry install --without dev --no-interaction \
    && rm -rf /root/.cache
COPY ./rbb_bot ./rbb_bot
COPY ./migrations ./migrations
# The runtime user cannot write __pycache__, so bytecode is compiled here or every
# start would recompile all imports. The user may only write the data directory,
# where the production log rotates; code and bundled data stay root-owned. Meme
# renders use /tmp.
RUN python -m compileall -q /usr/local/lib/python3.14/site-packages /app/rbb_bot /app/migrations > /dev/null \
    && chown rbb:rbb /app/rbb_bot/data
USER rbb
CMD ["python", "-m", "rbb_bot.container_start"]
