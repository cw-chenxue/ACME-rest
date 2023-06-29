FROM python:3.10.11-alpine3.16

WORKDIR code 

COPY ./requirements.txt /code/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY ./__init__.py /code/app/__init__.py
COPY ./main.py /code/app/main.py
 
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]