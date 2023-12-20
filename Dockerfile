FROM python:3.10
RUN apt-get update
RUN apt-get install -y ffmpeg
WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN pip install poetry
RUN poetry config virtualenvs.create false
RUN poetry install --without dev
RUN pip install yt-dlp
# RUN pip install TikTokApi
# RUN python -m playwright install
# RUN python -m playwright install-deps
CMD ["python", "./rbb_bot/launcher.py"]
