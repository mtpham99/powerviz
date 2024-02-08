FROM python:3.11-alpine

RUN apk update

WORKDIR /powerviz
COPY ./requirements.txt /powerviz/
RUN pip install -r ./requirements.txt

COPY . /powerviz/
RUN pip install .

RUN echo -e "* * * * * sh -c 'cd /powerviz && python3.11 /powerviz/scripts/update_db.py'\n" >> /etc/crontabs/root

CMD [ "/bin/sh", "-c", "/powerviz/scripts/run.sh" ]
