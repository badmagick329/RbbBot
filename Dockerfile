FROM python:3.10.10
RUN apt-get update
RUN apt-get install -y ffmpeg
WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN pip install poetry
RUN poetry config virtualenvs.create false
RUN poetry install --without dev
RUN pip install yt-dlp
COPY ./rbb_bot ./rbb_bot
COPY ./migrations ./migrations
CMD ["python", "-m", "rbb_bot.container_start"]
