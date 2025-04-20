from flask_wtf import FlaskForm
from wtforms import (StringField, IntegerField, FloatField,
                     SubmitField, FileField)
from wtforms.validators import DataRequired, Optional, NumberRange

class PersonForm(FlaskForm):
    first_name  = StringField("Имя", validators=[DataRequired()])
    last_name   = StringField("Фамилия", validators=[DataRequired()])
    patronymic  = StringField("Отчество", validators=[Optional()])
    age         = IntegerField("Возраст", validators=[Optional(), NumberRange(14, 99)])
    gender      = StringField("Пол", validators=[Optional()])
    education   = StringField("Образование", validators=[Optional()])
    position    = StringField("Должность", validators=[Optional()])
    experience  = IntegerField("Стаж (лет)", validators=[Optional(), NumberRange(0, 50)])
    salary      = FloatField("Зарплата", validators=[Optional()])
    phone       = StringField("Телефон", validators=[Optional()])
    address     = StringField("Адрес", validators=[Optional()])
    submit      = SubmitField("Сохранить")

class UploadForm(FlaskForm):
    file   = FileField("CSV‑файл", validators=[DataRequired()])
    submit = SubmitField("Загрузить")
