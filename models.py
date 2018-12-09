from peewee import SqliteDatabase, Model, TextField, DateTimeField, IntegerField, IntegrityError, BooleanField

db = SqliteDatabase('db.sqlite3')


class ActionScheduler(Model):
    action = TextField()
    datetime = DateTimeField()
    chat_id = IntegerField()
    message_id = IntegerField()

    class Meta:
        database = db


class User(Model):
    id = IntegerField(primary_key=True)
    username = TextField(unique=True)
    first_name = TextField()
    last_name = TextField()
    auth_token = TextField(null=True)
    auth = BooleanField(default=False)

    class Meta:
        database = db

    @staticmethod
    def cog(data):  # create or get
        try:
            with db.atomic():
                return User.create(id=data['id'],
                            username=data['username'],
                            first_name=data['first_name'],
                            last_name=data['last_name'])
        except IntegrityError as e:
            return User.get(User.id == data['id'])





