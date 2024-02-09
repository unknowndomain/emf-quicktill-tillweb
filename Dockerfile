FROM python:3.10
RUN apt-get update
RUN apt-get install -y --no-install-recommends libcups2-dev
RUN apt-get clean
RUN pip3 install poetry
RUN poetry config virtualenvs.create false
COPY pyproject.toml poetry.lock /app/
WORKDIR /app
RUN poetry install
STOPSIGNAL SIGINT
ENV USING_DOCKER=yes
ENV OAUTHLIB_INSECURE_TRANSPORT=1
ENV DJANGO_SETTINGS_MODULE=tillweb_infra.settings
CMD [ "docker/startup-dev.sh" ]
