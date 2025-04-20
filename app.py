from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.utils import secure_filename
import pandas as pd
import os
from statistics import median


app = Flask(__name__)
app.config.update(
    SECRET_KEY="super‑secret",
    SQLALCHEMY_DATABASE_URI="sqlite:///people.db",
    UPLOAD_FOLDER="uploads",
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,            # 5 МБ
)
db = SQLAlchemy(app)
with app.app_context():
    db.create_all()      # создаём все таблицы, если их нет
migrate = Migrate(app, db)

# ─────────────────────────────────────────────────────────── models & forms
from models import Person                                   # noqa: E402
from forms import PersonForm, UploadForm                    # noqa: E402

# ─────────────────────────────────────────────────────────── helpers
def csv_to_db(path: str):
    df = pd.read_csv(path)
    for _, row in df.iterrows():
        person = Person(
            first_name=row.get("Имя", ""),
            last_name=row.get("Фамилия", ""),
            patronymic=row.get("Отчество", ""),
            age=row.get("Возраст") or None,
            gender=row.get("Пол", ""),
            education=row.get("Уровень образования", ""),
            position=row.get("Должность", ""),
            experience=row.get("Стаж (лет)") or None,
            salary=row.get("Зарплата") or None,
            phone=row.get("Телефон", ""),
            address=row.get("Адрес", ""),
        )
        db.session.add(person)
    db.session.commit()

# ─────────────────────────────────────────────────────────── routes
@app.route("/")
def index():
    # лендинг
    return render_template("index.html")

# новая страница со списком
@app.route("/employees")
def employees():
    # читаем номер страницы из GET-параметра, по умолчанию 1
    page = request.args.get('page', 1, type=int)
    per_page = 20

    # используем paginate из Flask‑SQLAlchemy
    pagination = Person.query.order_by(Person.id) \
        .paginate(page=page, per_page=per_page, error_out=False)

    people = pagination.items  # те 20 сотрудников для текущей страницы

    return render_template(
        "employees.html",
        people=people,
        pagination=pagination
    )
@app.route("/employees/delete-all", methods=["POST"])
def delete_all_employees():
    try:
        # Удаляем все записи в таблице Person
        num = Person.query.delete()
        db.session.commit()
        flash(f"Удалено {num} сотрудников", "success")
    except Exception as e:
        db.session.rollback()
        flash("Ошибка при удалении сотрудников", "danger")
    return redirect(url_for("employees"))

@app.route("/add", methods=["GET", "POST"])
def add():
    form = PersonForm()
    if form.validate_on_submit():
        # Сначала собираем только нужные поля, исключая submit и csrf_token
        data = {
            field.name: field.data
            for field in form
            if field.name not in ("submit", "csrf_token")
        }
        person = Person(**data)
        db.session.add(person)
        db.session.commit()
        flash("Запись добавлена", "success")
        return redirect(url_for("employees"))
    return render_template("add.html", form=form)

@app.route("/upload", methods=["GET", "POST"])
def upload():
    form = UploadForm()
    if form.validate_on_submit():
        f = form.file.data
        filename = secure_filename(f.filename)
        upload_folder = app.config["UPLOAD_FOLDER"]
        os.makedirs(upload_folder, exist_ok=True)
        path = os.path.join(upload_folder, filename)
        f.save(path)

        # Проверяем обязательные столбцы в CSV
        try:
            df = pd.read_csv(path)
        except Exception as e:
            os.remove(path)
            flash("Не удалось прочитать CSV-файл: некорректный формат.", "danger")
            return redirect(url_for("upload"))

        required = ["Имя", "Фамилия", "Должность", "Стаж (лет)", "Зарплата"]
        missing = [col for col in required if col not in df.columns]
        if missing:
            os.remove(path)
            flash(
                "В загруженном CSV отсутствуют обязательные столбцы: "
                + ", ".join(missing),
                "danger"
            )
            return redirect(url_for("upload"))

        # Всё в порядке — импортируем в базу
        try:
            csv_to_db(path)
            flash(f"CSV импортирован успешно ({len(df)} записей).", "success")
        except Exception as e:
            flash("Ошибка при добавлении записей в базу.", "danger")
        return redirect(url_for("employees"))

    return render_template("upload.html", form=form)

from sklearn.linear_model import LinearRegression
import statsmodels.api as sm
import json, numpy as np, pingouin as pg   # pip install pingouin

@app.route("/analytics")
@app.route("/analytics")
def analytics():
    # Загружаем данные из БД
    df = pd.DataFrame([p.as_dict() for p in Person.query.all()])
    if df.empty:
        flash("Нет данных для аналитики.", "warning")
        return redirect(url_for("index"))

    # ==== 1. Базовые метрики ====
    avg_salary    = round(df["salary"].mean(),  0)
    median_salary = round(df["salary"].median(),0)
    mean_age      = round(df["age"].mean(),     1)
    mean_exper    = round(df["experience"].mean(),1)

    # ==== 2. Простая корреляция salary–experience ====
    corr_se = round(df[["salary", "experience"]]
                    .dropna()
                    .corr()
                    .iloc[0, 1], 3)

    # ==== 3. Частная корреляция (контроль edu + position) ====
    tmp = df.dropna(subset=["salary", "experience"]).copy()
    tmp["edu_code"] = tmp["education"].astype("category").cat.codes
    tmp["pos_code"] = tmp["position"].astype("category").cat.codes

    if len(tmp) >= 3:
        try:
            pc = pg.partial_corr(
                data=tmp,
                x="experience",
                y="salary",
                covar=["edu_code", "pos_code"],
                method="pearson"
            )
            row = pc.iloc[0]
            pcorr   = round(row["r"],     3)
            pcorr_p = round(row["p-val"], 3)
        except Exception:
            pcorr, pcorr_p = None, None
    else:
        pcorr, pcorr_p = None, None

    # ==== 4. OLS‑регрессия salary ~ experience ====
    reg_df = df.dropna(subset=["salary", "experience"])
    if len(reg_df) >= 2:
        X = sm.add_constant(reg_df["experience"])
        model = sm.OLS(reg_df["salary"], X).fit()
        intercept = round(model.params["const"],       0)
        slope     = round(model.params["experience"],  2)
        slope_p   = round(model.pvalues["experience"], 3)
        r2        = round(model.rsquared,              3)

        x_min, x_max = reg_df["experience"].agg(["min","max"])
        reg_line = [
            {"x": x_min, "y": intercept + slope * x_min},
            {"x": x_max, "y": intercept + slope * x_max},
        ]
    else:
        intercept = slope = slope_p = r2 = None
        reg_line = []

    # ==== 5. Данные для графиков ====
    corr_json   = json.dumps(df[["salary","experience","age"]]
                             .dropna().corr().round(3).to_dict())
    scatter     = json.dumps(df[["experience","salary"]]
                             .dropna().to_dict(orient="records"))
    reg_line_js = json.dumps(reg_line)

    box_gender = {
        g: df.loc[df.gender == g, "salary"].dropna().tolist()
        for g in df["gender"].unique()
    }
    age_hist = np.histogram(df["age"].dropna(),
                            bins=range(int(df["age"].min()),
                                       int(df["age"].max()) + 5, 5))
    age_hist_dict = {"x": age_hist[1].tolist(), "y": age_hist[0].tolist()}

    by_edu   = df.groupby("education")["salary"] \
                 .mean().round(0) \
                 .sort_values(ascending=False) \
                 .to_dict()
    top5     = df.groupby("position")["salary"] \
                 .mean().round(0) \
                 .sort_values(ascending=False) \
                 .head(5).to_dict()
    edu_cnt  = df["education"].value_counts().to_dict()

    # ==== 6. «Профессиональная» статистика ====
    s = df["salary"].dropna()
    salary_min, salary_max = int(s.min()), int(s.max())
    salary_std             = round(s.std(), 2)

    q1, q2, q3 = [int(x) for x in s.quantile([0.25, 0.5, 0.75])]
    iqr        = q3 - q1

    gender_means = df.dropna(subset=["salary","gender"]) \
                     .groupby("gender")["salary"].mean()
    mean_men     = round(gender_means.get("Мужчина", 0), 0)
    mean_wom     = round(gender_means.get("Женщина", 0), 0)
    gender_gap   = round(mean_wom / mean_men if mean_men else 0, 3)

    cut_low   = s.quantile(0.05)
    cut_high  = s.quantile(0.95)
    pct_low   = int((df["salary"] <= cut_low).sum())
    pct_high  = int((df["salary"] >= cut_high).sum())

    edu_mean = df.groupby("education")["salary"].mean().round(0).to_dict()
    edu_dev  = {edu: int(val - avg_salary) for edu, val in edu_mean.items()}

    # ==== Рендеринг шаблона ====
    return render_template("analytics.html",
        # KPI
        avg_salary=avg_salary, median_salary=median_salary,
        mean_age=mean_age,     mean_exper=mean_exper,
        # Корреляции и регрессия
        corr_se=corr_se,
        pcorr=pcorr, pcorr_p=pcorr_p,
        intercept=intercept, slope=slope,
        slope_p=slope_p, r2=r2,
        # Данные для JS‑графиков
        corr_json=corr_json,
        scatter=scatter,
        reg_line=reg_line_js,
        box_gender=json.dumps(box_gender),
        age_hist=json.dumps(age_hist_dict),
        by_edu=json.dumps(by_edu),
        top5=json.dumps(top5),
        edu_counts=json.dumps(edu_cnt),
        # Профессиональные метрики
        salary_min=salary_min, salary_max=salary_max,
        salary_std=salary_std,
        q1=q1, q2=q2, q3=q3, iqr=iqr,
        mean_men=mean_men, mean_wom=mean_wom,
        gender_gap=gender_gap,
        pct_low=pct_low, pct_high=pct_high,
        edu_dev=edu_dev
    )

# JSON API для JS‑графиков (если захочешь SPA)
@app.route("/api/people")
def api_people():
    return jsonify([p.as_dict() for p in Person.query.all()])
# app.py  (добавь в самый низ, после других маршрутов)
from sklearn.linear_model import LinearRegression
import statsmodels.stats.outliers_influence as sm_oi
import numpy as np, json


if __name__ == "__main__":
    app.run(debug=True)
