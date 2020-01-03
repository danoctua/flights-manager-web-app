from sqlalchemy import create_engine, String, Integer, Column, DateTime, Boolean, Text, desc, func, ForeignKey, \
    ForeignKeyConstraint, Float, Time, Date
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.exc import IntegrityError, DisconnectionError, ProgrammingError, OperationalError
from sqlalchemy.orm import sessionmaker, relationship, scoped_session, backref
from sqlalchemy.ext.hybrid import hybrid_property, hybrid_method
from sqlalchemy.sql.expression import false, true, case, not_, and_
import os, numpy, datetime, warnings, time, random, json
from multiprocessing import Process, Manager, Semaphore
from multiprocessing.managers import BaseManager
from contextlib import contextmanager

from flask import Flask, url_for, render_template, abort, request, redirect, make_response
from flask_sqlalchemy import SQLAlchemy
import urllib, re
from passlib.hash import bcrypt
from string import ascii_letters, digits

app = Flask(__name__)

with open("data/db_credentials") as file:
    db_credentials = json.load(file)

#   Go to the data/db_credentials file
# | data
# | --> db_credentials
#   and replace credentials with your created before


app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://{username}:{password}@{host}/{db_name}?charset=utf8'.format(
    username=db_credentials['username'],
    password=db_credentials['password'],
    host=db_credentials['host'],
    db_name=db_credentials['database_name']
)

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

dir_path = os.path.dirname(os.path.realpath(__file__))


def check_empty(x):
    if isinstance(x, list):
        if all([y != "" for y in x]):
            return False
    return True


@contextmanager
def session_handler():
    session = db.session
    try:
        session.flush()
        yield session
        session.commit()
    except IntegrityError as exp:
        print("Already exists", exp)
        session.rollback()
    except Exception as exp:
        print(exp)
        session.rollback()


def get_countries_list():
    with open(os.path.join(dir_path, "data", "countries")) as file:
        ls = file.read().splitlines()
        return ls


days_pl = {
    0: "Poniedziałek",
    1: "Wtorek",
    2: "Środa",
    3: "Czwartek",
    4: "Piątek",
    5: "Sobota",
    6: "Niedziela"
}


class User(db.Model):
    __tablename__ = 'user'

    user_id = Column('id_u', Integer, primary_key=True, autoincrement=True)
    haslo = Column('haslo', String(300), nullable=False)
    typ = Column('typ', String(32), default='user')
    email = Column('email', String(32), nullable=False)
    imie = Column('imie', String(32), nullable=False)
    nazwisko = Column('nazwisko', String(32), nullable=False)
    token = Column("token", String(64), nullable=False)

    def __init__(self, email, password, name, surname, type):
        self.email = email
        self.haslo = bcrypt.encrypt(password)
        self.imie = name
        self.nazwisko = surname
        self.typ = type
        self.token = "".join([random.choice(ascii_letters + digits) for _ in range(64)])

    def validate_password(self, password):
        return bcrypt.verify(password, self.haslo)

    rabat = relationship("Rabat", cascade="all")
    podroz = relationship("Podroz", cascade="all")

    def is_admin(self):
        return self.typ == 'admin'

    def get_type(self):
        return "Użytkownik" if self.typ == "user" else "Administrator"


class Rabat(db.Model):
    __tablename__ = 'rabat'

    kod = Column('kod', String(10), primary_key=True, nullable=False)
    procent = Column('procent', Integer, nullable=False)
    data_waznosci = Column('data_waznosci', DateTime, nullable=False)

    user_id = Column("user_id_u", Integer, ForeignKey(User.user_id), nullable=False)
    user = relationship("User")


class LiniaLotnicza(db.Model):
    __tablename__ = 'linia_lotnicza'

    nazwa = Column('nazwa', String(25), primary_key=True, nullable=False)
    kraj = Column('kraj', String(25))
    data_zalozenia = Column('data_zalozenie', DateTime, nullable=False)

    samolot = relationship('Samolot', cascade="all")
    pilot = relationship('Pilot', cascade='all')
    harmonogram = relationship("Harmonogram", cascade='all')

    def liczba_samolotow(self):
        return pokaz_samoloty_linia(self.nazwa)

    def get_data_zalozenia(self):
        return datetime.datetime.strftime(self.data_zalozenia, "%d.%m.%Y")

    def get_nazwa_safe(self):
        return urllib.parse.quote(self.nazwa.replace(" ", "_"))


class Samolot(db.Model):
    __tablename__ = 'samolot'

    nr_boczny = Column('nr_boczny', String(10), primary_key=True, nullable=False)
    max_zasieg = Column('max_zasieg', Integer, default=0)
    marka = Column('marka', String(15), nullable=False)
    model = Column('model', String(15), nullable=False)
    przebieg = Column('przebieg', Integer, default=0)
    pojemnosc = Column('pojemnosc', Integer, nullable=False)

    linia_lotnicza_nazwa = Column('linia_lotnicza_nazwa', String(25), ForeignKey(LiniaLotnicza.nazwa), nullable=False)
    linia_lotnicza = relationship('LiniaLotnicza')
    realizacja_lotu = relationship('RealizacjaLotu')


class Pilot(db.Model):
    __tablename__ = 'pilot'

    id_pil = Column('id_pil', Integer, primary_key=True, autoincrement=True)
    imie = Column('imie', String(30), nullable=False)
    nazwisko = Column('nazwisko', String(30), nullable=False)
    data_dolaczenia = Column('data_dolaczenia', DateTime)

    linia_lotnicza_nazwa = Column('linia_lotnicza_nazwa', String(25), ForeignKey(LiniaLotnicza.nazwa), nullable=False)
    linia_lotnicza = relationship('LiniaLotnicza')

    realizacja1 = relationship("RealizacjaLotu", foreign_keys="[RealizacjaLotu.pilot_id_pil1]", cascade="all")
    realizacja2 = relationship("RealizacjaLotu", foreign_keys="[RealizacjaLotu.pilot_id_pil2]", cascade="all")


class Lotnisko(db.Model):
    __tablename__ = 'lotnisko'

    kod = Column('kod_miedzynarodowy', String(4), primary_key=True)
    m_na_mapie = Column('miejsce_na_mapie', String(100), nullable=False)
    kraj = Column('kraj', String(30), nullable=False)
    miasto = Column('miasto', String(20), nullable=False)
    strefa_czasowa = Column('strefa_czasowa', Integer, nullable=False)

    harmonogram_start = relationship("Harmonogram", foreign_keys="[Harmonogram.start_lotnisko_nazwa]",
                                     cascade="all")
    harmonogram_finish = relationship("Harmonogram", foreign_keys="[Harmonogram.finish_lotnisko_nazwa]",
                                      cascade="all")


class Harmonogram(db.Model):
    __tablename__ = 'harmonogram'

    nr_lotu = Column("nr_lotu", String(8), primary_key=True)
    dzien_tygodnia = Column("dzien_tygodnia", Integer, nullable=False)
    start_godzina = Column("start_godzina", Time, nullable=False)
    # czas_trwania = Column("trwanie", Integer, nullable=False)
    finish_godzina = Column("finish_godzina", Time, nullable=False)
    cena_podstawowa = Column("cena_podstawowa", Float(precision=2), nullable=False)

    start_lotnisko_nazwa = Column("start_lotnisko", ForeignKey(Lotnisko.kod), nullable=False)
    start_lotnisko = relationship("Lotnisko", foreign_keys=[start_lotnisko_nazwa])

    finish_lotnisko_nazwa = Column("finish_lotnisko", ForeignKey(Lotnisko.kod), nullable=False)
    finish_lotnisko = relationship("Lotnisko", foreign_keys=[finish_lotnisko_nazwa],
                                   backref=backref("finish_lotnisko_nazwa"))

    linia_lotnicza_nazwa = Column("linia_lotnicza", ForeignKey(LiniaLotnicza.nazwa), nullable=False)
    linia_lotnicza = relationship("LiniaLotnicza", foreign_keys=[linia_lotnicza_nazwa])

    realizacja_lotu = relationship("RealizacjaLotu", cascade="all")

    def get_dzien_tygodnia(self):
        return days_pl[self.dzien_tygodnia]

    def get_start_godzina(self):
        return datetime.time.strftime(self.start_godzina, "%H:%M")

    def get_finish_godzina(self):
        return datetime.time.strftime(self.finish_godzina, "%H:%M")


class Podroz(db.Model):
    __tablename__ = 'podroz'

    nr_rezerwacji = Column('nr_rezerwacji', Integer, primary_key=True, autoincrement=True)
    cena = Column('cena', Float(2), nullable=False)

    user_id_u = Column('user_id_u', Integer, ForeignKey(User.user_id), nullable=False)
    user = relationship('User')

    polaczenie = relationship('Polaczenie')


class RealizacjaLotu(db.Model):
    __tablename__ = 'realizacja_lotu'

    id_rlotu = Column('id_rlotu', Integer, primary_key=True, autoincrement=True)
    data = Column('data', Date, nullable=False)
    ilosc_pasazerow = Column('ilosc_pasazerow', Integer, nullable=False)

    harmonogram_nr_lotu = Column('harmonogram_nr_lotu', String(9), ForeignKey(Harmonogram.nr_lotu), nullable=False)
    harmonogram = relationship('Harmonogram')

    samolot_nr_boczny = Column('samolot_nr_boczny', String(10), ForeignKey(Samolot.nr_boczny))
    samolot = relationship('Samolot')

    pilot_id_pil1 = Column("pilot_id_pil1", ForeignKey(Pilot.id_pil))
    pilot1 = relationship("Pilot", foreign_keys=[pilot_id_pil1])

    pilot_id_pil2 = Column("pilot_id_pil2", ForeignKey(Pilot.id_pil))
    pilot2 = relationship("Pilot", foreign_keys=[pilot_id_pil2], backref=backref("pilot_id_pil2"))


class Polaczenie(db.Model):
    __tabelname__ = 'polaczenie'

    nr_miejsca = Column('nr_miejsca', String(3), nullable=False)
    bagaz = Column('bagaz', String(5), nullable=False)
    kolejnosc = Column('kolejnosc', Integer, nullable=False)

    realizacja_lotu_id_rlotu = Column('realizacja_lotu_id_rlotu',
                                      Integer, ForeignKey(RealizacjaLotu.id_rlotu), primary_key=True, nullable=False)
    realizacja_lotu = relationship('RealizacjaLotu')

    podroz_nr_rezerwacji = Column('podroz_nr_rezerwacji', Integer,
                                  ForeignKey(Podroz.nr_rezerwacji), primary_key=True, nullable=False)
    podroz = relationship('Podroz')


##############################################
#           FUNKCJE
##############################################

def convert_time_front_back(time_str):
    try:
        time_f = datetime.datetime.strptime(time_str, "%H:%M").time()
        return time_f
    except:
        try:
            time_f = datetime.datetime.strptime(time_str, "%H:%M:%S").time()
            return time_f
        except:
            return None


# ######### samoloty

def pokaz_samoloty_linia(nazwa):
    with session_handler() as db_session:
        liczba = len(db_session.query(Samolot).filter(Samolot.linia_lotnicza_nazwa == nazwa).all())
        return liczba


def check_data_samolot(nr_boczny, marka, model, linia_nazwa, pojemnosc):
    with session_handler() as db_session:
        samolot = db_session.query(Samolot).filter(Samolot.nr_boczny == nr_boczny).first()
        if samolot:
            return ['danger',
                    f"Samolot z numerem bocznym {nr_boczny} już istnieje ({samolot.linia_lotnicza_nazwa})"]
        if len(marka) > 15 or len(model) > 15:
            return ['danger', "Długość atrybutów marka i model powinna być nie większa niż 15"]
        if not pokaz_linie(linia_nazwa):
            return ['danger', f"Linia lotnicza {linia_nazwa} nie istnieje. Spróbuj jeszcze raz"]
        if not isinstance(pojemnosc, int):
            if isinstance(pojemnosc, str):
                if not pojemnosc.isnumeric():
                    return ['danger', "Pojemnośc powinna być liczbą"]
            else:
                return ['danger', "Pojemnośc powinna być liczbą"]
        return None


def dodaj_samolot(nr_boczny, marka, model, linia_nazwa, pojemnosc, zasieg=None):
    error = check_data_samolot(nr_boczny, marka, model, linia_nazwa, pojemnosc)
    if error:
        return error
    with session_handler() as db_session:
        pojemnosc = int(pojemnosc)
        nowy_samolot = Samolot(nr_boczny=nr_boczny, marka=marka, model=model, pojemnosc=pojemnosc,
                               linia_lotnicza_nazwa=linia_nazwa, max_zasieg=zasieg)
        db_session.add(nowy_samolot)
        db_session.commit()
        return ['success', "Samolot został dodany"]


def zmodyfikuj_samolot(nr_boczny, marka, model, linia_nazwa, pojemnosc, zasieg=None):
    error = check_data_samolot(nr_boczny, marka, model, linia_nazwa, pojemnosc)
    if error:
        return error
    with session_handler() as db_session:
        pojemnosc = int(pojemnosc)
        samolot = db_session.query(Samolot).filter(Samolot.nr_boczny == nr_boczny).first()
        if not samolot:
            return ['danger', f"Samolot o numerze bocznym {nr_boczny} nie istnieje"]
        samolot.marka = marka
        samolot.model = model
        samolot.pojemnosc = pojemnosc
        samolot.linia_lotnicza_nazwa = linia_nazwa
        samolot.max_zasieg = zasieg
        return ['success', f"Dane o samolocie {nr_boczny} zostały zmodyfikowane"]


def usun_samolot(nr_boczny):
    with session_handler() as db_session:
        samolot = db_session.query(Samolot).filter(Samolot.nr_boczny == nr_boczny).first()
        if not samolot:
            return ['danger', f'Samolot o numerze bocnzym {nr_boczny} nie istnieje']
        db_session.delete(samolot)
        return ['success', f"Samolot o numerze bocznym {nr_boczny} został usunięty"]


def pokaz_samoloty(linia=None):
    with session_handler() as db_session:
        if linia:
            samoloty = db_session.query(Samolot).filter(Samolot.linia_lotnicza_nazwa == linia).all()
        else:
            samoloty = db_session.query(Samolot).all()
        return samoloty


# ######## linie


def dodaj_linie(nazwa, kraj=None, data_zalozenia=datetime.datetime.now()):
    with session_handler() as db_session:
        linia_nazwa = db_session.query(LiniaLotnicza).filter(LiniaLotnicza.nazwa == nazwa).first()
        if linia_nazwa:
            return ['danger', "Linia lotnicza z taką nazwą już istnieje"]
        nowa_linia = LiniaLotnicza(nazwa=nazwa, kraj=kraj, data_zalozenia=data_zalozenia)
        db_session.add(nowa_linia)
        return ['success', "Linia została dodana"]


def usun_linie(nazwa):
    with session_handler() as db_session:
        linia = db_session.query(LiniaLotnicza).filter(LiniaLotnicza.nazwa == nazwa).first()
        if not linia:
            return ['danger', "Nie istnieje linii lotniczej o podanej nazwie"]
        db_session.delete(linia)
        return ['success', "Linia została usunięta"]


def pokaz_linie(line=None):
    with session_handler() as db_session:
        if line:
            linie = db_session.query(LiniaLotnicza).filter(LiniaLotnicza.nazwa == line).first()
        else:
            linie = db_session.query(LiniaLotnicza).all()
        return linie


def zmodyfikuj_linie(nazwa, new_nazwa, new_kraj):
    with session_handler() as db_session:
        linia = db_session.query(LiniaLotnicza).filter(LiniaLotnicza.nazwa == nazwa).first()
        if not linia:
            return ['danger', "Linia lotnicza z taką nazwą nie istnieje"]
        linia.nazwa = new_nazwa
        linia.kraj = new_kraj
        return ['success', f"Dane o linii {nazwa} zostały zmodyfikowane"]


# ######## piloci


def pokaz_pilotow(linia=None):
    with session_handler() as db_session:
        if linia:
            piloci = db_session.query(Pilot).filter(Pilot.linia_lotnicza_nazwa == linia).all()
        else:
            piloci = db_session.query(Pilot).all()
        return piloci


def check_data_pilot(imie, nazwisko):
    if not isinstance(imie, str) or not isinstance(nazwisko, str):
        return ['danger', "Niepoprawny format dla pól imię i nazwisko"]
    if len(imie) > 30 or len(nazwisko) > 30:
        return ['danger', "Imię lub nazwisko ma długość większą niż to jest dozwolone (30 znaków)"]


def dodaj_pilota(imie, nazwisko, linia_nazwa):
    res = check_data_pilot(imie, nazwisko)
    if res:
        return res
    with session_handler() as db_session:
        nowy_pilot = Pilot(imie=imie, nazwisko=nazwisko, data_dolaczenia=datetime.datetime.now(),
                           linia_lotnicza_nazwa=linia_nazwa)
        db_session.add(nowy_pilot)
        return ['success', 'Nowy pilot został dodany']


def usun_pilota(id_pil):
    with session_handler() as db_session:
        pilot = db_session.query(Pilot).filter(Pilot.id_pil == id_pil).first()
        if not pilot:
            return ['danger', f"Pilot o identyfikatorze {id_pil} nie istnieje"]
        else:
            name = pilot.imie
            surname = pilot.nazwisko
            db_session.delete(pilot)
            return ["success", f"Pilot {name} {surname} został usunięty"]


def zmodyfikuj_pilota(id_pil, imie, nazwisko):
    res = check_data_pilot(imie, nazwisko)
    if res:
        return res
    with session_handler() as db_session:
        pilot = db_session.query(Pilot).filter(Pilot.id_pil == id_pil).first()
        if not pilot:
            return ["danger", f"Pilot o id {id_pil} nie istnieje"]
        pilot.imie = imie
        pilot.nazwisko = nazwisko
        return ["success", f"Dane pilota {imie} {nazwisko} zostały zmienione"]


# ############### lotniska


def pokaz_lotniska():
    with session_handler() as db_session:
        result = db_session.query(Lotnisko).order_by(Lotnisko.kod).all()
        return result


def check_data_lotnisko(kod, m_na_mapie, kraj, miasto, strefa_czasowa):
    if any([x == "" for x in [kod, m_na_mapie, kraj, miasto, strefa_czasowa]]):
        return ['danger', "Żadne pole nie może być puste"]
    if len(kod) > 4:
        return ["danger", "Długość kodu międzynarodowego jest większa od dozwolonej (4)"]
    if len(m_na_mapie) > 100:
        return ["danger", "Długość miejsca na mapie jest większa od dozwolonej (100)"]
    if len(kraj) > 30:
        return ["danger", "Długość nazwy kraju jest większa od dozwolonej (30)"]
    if len(miasto) > 20:
        return ["danger", "Długość nazwy miasta jest większa od dozwolonej (20)"]
    if not isinstance(strefa_czasowa, str):
        return ["danger", "Strefa czasowa jest pusta"]
    if not strefa_czasowa.isnumeric():
        return ['danger', "Strefa czasowa musi być liczbą"]
    return None


def dodaj_lotnisko(kod, m_na_mapie, kraj, miasto, strefa_czasowa):
    error = check_data_lotnisko(kod, m_na_mapie, kraj, miasto, strefa_czasowa)
    if error:
        return error
    with session_handler() as db_session:
        ex_lotnisko = db_session.query(Lotnisko).filter(Lotnisko.kod == kod).first()
        if ex_lotnisko:
            return ['danger', "Lotnisko z podanym kodem międzynarodowym już zostało dodane"]
        new_lotnisko = Lotnisko(kod=kod, m_na_mapie=m_na_mapie, kraj=kraj, miasto=miasto, strefa_czasowa=strefa_czasowa)
        db_session.add(new_lotnisko)
        return ['success', f"Lotnisko {kod} zostało dodane"]


def zmodyfikuj_lotnisko(kod, nowy_kod, m_na_mapie, kraj, miasto, strefa_czasowa):
    check_data_lotnisko(nowy_kod, m_na_mapie, kraj, miasto, strefa_czasowa)
    with session_handler() as db_session:
        ex_lotnisko = db_session.query(Lotnisko).filter(Lotnisko.kod == kod).first()
        if not ex_lotnisko:
            return ['danger', f"Lotnisko o kodzie międzynarodowym {kod} nie istnieje"]
        # if kod != nowy_kod:
        ex_lotnisko.kod = nowy_kod
        ex_lotnisko.m_na_mapie = m_na_mapie
        ex_lotnisko.kraj = kraj
        ex_lotnisko.miasto = miasto
        ex_lotnisko.strefa_czasowa = strefa_czasowa
        return ['success', f"Lotnisko o kodzie międzynarodowym {nowy_kod} zostało zmienione"]
    pass


def usun_lotnisko(kod):
    with session_handler() as db_session:
        lotnisko = db_session.query(Lotnisko).filter(Lotnisko.kod == kod).first()
        if lotnisko:
            db_session.delete(lotnisko)
            return ['success', f"Lotnisko {kod} zostało usunięte"]
        else:
            return ['danger', f"Lotnisko o kodzie {kod} nie istnieje"]


# ############# harmonogram

def check_data_harmonogram(nr_lotu, linia_lotnicza, start_lotnisko, finish_lotnisko, dzien_tygodnia, start_godzina,
                           finish_godzina, cena_podstawowa):
    if check_empty([linia_lotnicza, start_lotnisko, finish_lotnisko, dzien_tygodnia, start_godzina, finish_godzina,
                    cena_podstawowa]):
        return ['danger', "Wszystkie pola są obowiązkowe"]
    if len(nr_lotu) != 8:
        return ["danger", "Długośc numeru lotu musi być równa 8"]
    if not isinstance(dzien_tygodnia, str) or not dzien_tygodnia.isnumeric() or int(dzien_tygodnia) not in range(7):
        return ['danger', "Niepoprawny dzień tygodnia"]
    if not all([convert_time_front_back(x) for x in [start_godzina, finish_godzina]]):
        return ['danger', "Niepoprawny format godziny startu bądż lądowania"]
    try:
        float(cena_podstawowa)
    except ValueError:
        return ["danger", "Niepoprawny format ceny"]
    if start_lotnisko == finish_lotnisko:
        return ['danger', "Lotnisko startu nie może być takie same jak lotnisko lądowania"]


def pokaz_harmonogram(linia_lotnicza=None, nr_lotu=None):
    with session_handler() as db_session:
        if linia_lotnicza:
            result = db_session.query(Harmonogram).filter(Harmonogram.linia_lotnicza_nazwa == linia_lotnicza).order_by(
                Harmonogram.nr_lotu).all()
        elif nr_lotu:
            result = db_session.query(Harmonogram).filter(Harmonogram.nr_lotu == nr_lotu).first()
        else:
            # if it doesn't work - log into your root account on mysql and enter:
            #           SET GLOBAL sql_mode=(SELECT REPLACE(@@sql_mode,'ONLY_FULL_GROUP_BY',''));
            result = db_session.query(Harmonogram).group_by(Harmonogram.linia_lotnicza_nazwa).order_by(
                Harmonogram.nr_lotu).all()
        return result


def dodaj_harmonogram(nr_lotu, linia_lotnicza, start_lotnisko, finish_lotnisko, dzien_tygodnia, start_godzina,
                      finish_godzina, cena_podstawowa):
    error = check_data_harmonogram(nr_lotu, linia_lotnicza, start_lotnisko, finish_lotnisko, dzien_tygodnia,
                                   start_godzina,
                                   finish_godzina, cena_podstawowa)
    if error:
        return error
    with session_handler() as db_session:
        if db_session.query(Harmonogram).filter(Harmonogram.nr_lotu == nr_lotu).first():
            return ['danger', "Lot o danym numerze już istnieje"]
        for lotnisko in [start_lotnisko, finish_lotnisko]:
            if not db_session.query(Lotnisko).filter(Lotnisko.kod == lotnisko).first():
                return ["danger", f"Lotnisko o kodzie międzynarodowym {lotnisko} nie istnieje"]
        if not db_session.query(LiniaLotnicza).filter(LiniaLotnicza.nazwa == linia_lotnicza).first():
            return ["danger", f"Linia lotnicza o nazwie {linia_lotnicza} nie istnieje"]
        time_start = convert_time_front_back(start_godzina)
        time_finish = convert_time_front_back(finish_godzina)

        new_harmonogram = Harmonogram(nr_lotu=nr_lotu, linia_lotnicza_nazwa=linia_lotnicza, start_godzina=time_start,
                                      finish_godzina=time_finish, start_lotnisko_nazwa=start_lotnisko,
                                      dzien_tygodnia=int(dzien_tygodnia), finish_lotnisko_nazwa=finish_lotnisko,
                                      cena_podstawowa=float(cena_podstawowa))
        db_session.add(new_harmonogram)
        return ["success", f"Nowy wpis o numerze lotu {nr_lotu} został dodany"]


def usun_harmonogram(nr_lotu):
    with session_handler() as db_session:
        harmonogram = db_session.query(Harmonogram).filter(Harmonogram.nr_lotu == nr_lotu).first()
        if not harmonogram:
            return ["danger", f"Lot o numerze {nr_lotu} nie istnieje"]
        else:
            db_session.delete(harmonogram)
            return ["success", f"Lot o numerze {nr_lotu} został usunięty"]


def zmodyfikuj_harmonogram(nr_lotu, linia_lotnicza, start_lotnisko, finish_lotnisko, dzien_tygodnia,
                           start_godzina,
                           finish_godzina, cena_podstawowa):
    error = check_data_harmonogram(nr_lotu, linia_lotnicza, start_lotnisko, finish_lotnisko, dzien_tygodnia,
                                   start_godzina,
                                   finish_godzina, cena_podstawowa)
    if error:
        return error
    with session_handler() as db_session:
        harm_note = db_session.query(Harmonogram).filter(Harmonogram.nr_lotu == nr_lotu).first()
        if not harm_note:
            return ['danger', "Lot o danym numerze nie istnieje"]
        for lotnisko in [start_lotnisko, finish_lotnisko]:
            if not db_session.query(Lotnisko).filter(Lotnisko.kod == lotnisko).first():
                return ["danger", f"Lotnisko o kodzie międzynarodowym {lotnisko} nie istnieje"]
        if not db_session.query(LiniaLotnicza).filter(LiniaLotnicza.nazwa == linia_lotnicza).first():
            return ["danger", f"Linia lotnicza o nazwie {linia_lotnicza} nie istnieje"]
        time_start = convert_time_front_back(start_godzina)
        time_finish = convert_time_front_back(finish_godzina)
        harm_note.linia_lotnicza_nazwa = linia_lotnicza
        harm_note.start_godzina = time_start
        harm_note.finish_godzina = time_finish
        harm_note.start_lotnisko_nazwa = start_lotnisko
        harm_note.finish_lotnisko_nazwa = finish_lotnisko
        harm_note.dzien_tygodnia = int(dzien_tygodnia)
        harm_note.cena_podstawowa = float(cena_podstawowa)
        db_session.commit()
        return ['success', f"Lot o numerze {nr_lotu} został zmodyfikowany"]


# ############ user

def pokaz_user(user_id=None, email=None):
    with session_handler() as db_session:
        if user_id:
            result = db_session.query(User).filter(User.user_id == user_id).first()
        elif email:
            result = db_session.query(User).filter(User.email == email).first()
        else:
            result = db_session.query(User).all()
        return result


def dodaj_user(imie, nazwisko, email, password, password_repeat, u_type):
    if check_empty([imie, nazwisko, email, password, password_repeat, type]):
        return ["danger", "Wszystkie atrybuty są obowiązkowe"]
    if not isinstance(email, str) or email.index("@") == -1:
        return ['danger', "Niepoprawny format email"]
    if not re.search(r'\d', password) or not re.search(r'[A-Z]', password) or not re.search(r'[a-z]', password):
        return ["danger",
                "Hasło jest bardzo słabe. Musi zawierać conajmniej 1 liczbę, co najmniej 1 dużą literę i co najmniej jedbą małą"]
    if password != password_repeat:
        return ["danger", "Hasła wprowadzone w dwóch polach nie są równe"]
    if u_type not in ["user", "admin"]:
        return ["danger", "Niepoprawny typ hasła"]
    with session_handler() as db_session:
        ex_user = db_session.query(User).filter(User.email == email).first()
        if ex_user:
            return ['danger', "Użytkownik o podanym email już istnieje"]
        new_user = User(name=imie, surname=nazwisko, email=email, password=password, type=u_type)
        db_session.add(new_user)
        return ["success", "Użytkownik został dodany"]
    pass


def usun_user(user_id):
    with session_handler() as db_session:
        user = db_session.query(User).filter(User.user_id == user_id).first()
        if not user:
            return ["danger", "Użytkownik o danym identyfikatorze nie istnieje"]
        else:
            name = user.imie
            surname = user.nazwisko
            db_session.delete(user)
            return ["success", f"Użytkownik {name} {surname} został usunięty"]


def check_user_credentials(email, password):
    with session_handler() as db_session:
        user = db_session.query(User).filter(User.email == email).first()
        if not user:
            return None, ["danger", "Użytkownik z takim email nie istnieje"]
        if not user.validate_password(password):
            return None, ["danger", "Niepoprawne hasło"]
        return user, None


# ############ realizacja lotu

def check_data_realizacje_lotu(data, numer_lotu, samolot, pilot1, pilot2):
    if check_empty([data, numer_lotu, samolot, pilot1, pilot2]):
        return ["danger", "Wszystkie atrybuty są obowiązkowe"]
    try:
        print(data)
        data_f = datetime.datetime.strptime(data, "%d")

    except:
        return ['danger', "Niepoprawny format daty"]


def pokaz_realizacje_lotow(data=None, start=None, finish=None, nr_lotu=None, old_too=False):
    with session_handler() as db_session:
        if data and start and finish:
            realizacja_lotow = db_session.query(RealizacjaLotu, Harmonogram). \
                filter(RealizacjaLotu.harmonogram_nr_lotu == Harmonogram.nr_lotu). \
                filter(RealizacjaLotu.data == data and Harmonogram.start_lotnisko_nazwa == start and
                       Harmonogram.finish_lotnisko_nazwa == finish).all()
        elif nr_lotu:
            if old_too:
                realizacja_lotow = db_session.query(RealizacjaLotu).filter(
                    RealizacjaLotu.harmonogram_nr_lotu == nr_lotu).order_by(RealizacjaLotu.data).all()
            else:
                realizacja_lotow = db_session.query(RealizacjaLotu).filter(
                    RealizacjaLotu.harmonogram_nr_lotu == nr_lotu,
                    RealizacjaLotu.data >= datetime.datetime.now().date()).order_by(RealizacjaLotu.data).all()
        else:
            if old_too:
                realizacja_lotow = db_session.query(RealizacjaLotu).order_by(RealizacjaLotu.nr_lotu,
                                                                             RealizacjaLotu.data).all()
            else:
                realizacja_lotow = db_session.query(RealizacjaLotu).filter(
                    RealizacjaLotu.data >= datetime.datetime.now().date()).order_by(RealizacjaLotu.nr_lotu,
                                                                                    RealizacjaLotu.data).all()
        return realizacja_lotow


def dodaj_realizacje_lotu(data, numer_lotu, samolot, pilot1, pilot2):
    error = check_data_realizacje_lotu(data, numer_lotu, samolot, pilot1, pilot2)
    if error:
        return error
    with session_handler() as db_session:
        if db_session.query(RealizacjaLotu).filter(RealizacjaLotu.data == data
                                                   and RealizacjaLotu.harmonogram_nr_lotu == numer_lotu).first():
            return ['danger', "Lot o danym numerze w tym dniu już istnieje"]
        if not db_session.query(Samolot).filter(Samolot.nr_boczny == samolot).first():
            return ['danger', "Brak samoloru o podanym numerze"]
        if not db_session.query(Harmonogram).filter(Harmonogram.nr_lotu == numer_lotu).first():
            return ['danger', "Brak lotu o podanym numerze"]
        for pilot in [pilot1, pilot2]:
            if not db_session.query(Pilot).filter(Pilot.id_pil == pilot).first():
                return ["danger", "Pilot o danym identyfikatorze nie istnieje"]
        nowa_realizacja_lotu = RealizacjaLotu(data=data, harmonogram_nr_lotu=numer_lotu, samolot_nr_boczny=samolot,
                                              pilot_id_pil1=pilot1, pilot_id_pil2=pilot2, ilosc_pasazerow=0)

        db_session.add(nowa_realizacja_lotu)
        return ["success", f"Nowa realizacja lotu {numer_lotu} w dniu {data} została dodana"]


def usun_realizacje_lotu(data, numer):
    with session_handler() as db_session:
        realizacja = db_session.query(RealizacjaLotu).filter(RealizacjaLotu.data == data
                                                             and RealizacjaLotu.harmonogram_nr_lotu == numer).first()
        if not realizacja:
            return ["danger", f"Brak realizacji lotu {numer} w dniu {data}"]
        else:
            db_session.delete(realizacja)
            return ["success", f"Lot o numerze {numer} w dniu {data} został usunięty"]


def zmodyfikuj_realizacje_lotu(data, numer, new_samolot, new_pilot1, new_pilot2):
    if check_empty([new_samolot, new_pilot1, new_pilot2]):
        return ["danger", "Wszystkie atrybuty są obowiązkowe"]
    if not (new_pilot1.isnumeric() and new_pilot2.isnumeric()):
        return ["danger", "Podano zły identyfikator pilota"]
    with session_handler() as db_session:
        realizacja = db_session.query(RealizacjaLotu).filter(RealizacjaLotu.data == data and
                                                             RealizacjaLotu.harmonogram_nr_lotu == numer).first()
        if not realizacja:
            return ["danger", f"Brak realizacji lotu {numer} w dniu {data}"]
        realizacja.samolot_nr_boczny = new_samolot
        realizacja.pilot_id_pil1 = new_pilot1
        realizacja.pilot_id_pil2 = new_pilot2
        db_session.commit()
        return ['success', f"Realizacja lotu o numerze {numer} w dniu {data} została zmodyfikowana"]


WEEKS_TO_SCHEDULE = 20


def zauktualizuj_realizacje_lotow():
    today_weekday = datetime.datetime.now().weekday()
    with session_handler() as db_session:
        ex_realizacje = db_session.query(RealizacjaLotu)
        ex_harmonogram = db_session.query(Harmonogram).all()
        for harm_note in ex_harmonogram:
            for week in range(WEEKS_TO_SCHEDULE):
                tmp = datetime.datetime.now().date() + datetime.timedelta(
                    days=week * 7 - today_weekday + harm_note.dzien_tygodnia)
                if not ex_realizacje.filter(RealizacjaLotu.data == tmp).first():
                    new_note = RealizacjaLotu(data=tmp, ilosc_pasazerow=0, harmonogram_nr_lotu=harm_note.nr_lotu)
                    db_session.add(new_note)
    return ['success', "Wszystkie brakujące realizacje lotów zostali wygenerowane. Uzupełnij ręcznie pilotów i samoloty"]


db.create_all()

if __name__ == '__main__':
    # db.drop_all()
    pass
