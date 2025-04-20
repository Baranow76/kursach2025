from app import db

class Person(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    first_name  = db.Column(db.String(64))
    last_name   = db.Column(db.String(64))
    patronymic  = db.Column(db.String(64))
    age         = db.Column(db.Integer)
    gender      = db.Column(db.String(16))
    education   = db.Column(db.String(64))
    position    = db.Column(db.String(128))
    experience  = db.Column(db.Integer)
    salary      = db.Column(db.Float)
    phone       = db.Column(db.String(32))
    address     = db.Column(db.String(256))

    def as_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
