from enum import Enum


class Subject(str, Enum):
    AARDRIJKSKUNDE = "Aardrijkskunde"
    BEDRIJFSECONOMIE = "Bedrijfseconomie"
    BIOLOGIE = "Biologie"
    DUITS = "Duits"
    ECONOMIE = "Economie"
    ENGELS = "Engels"
    FRANS = "Frans"
    GESCHIEDENIS = "Geschiedenis"
    GRIEKS = "Grieks"
    LATIJN = "Latijn"
    LEVENS_BESCHOUWING = "Levens beschouwing"
    MAATSCHAPPIJLEER = "Maatschappijleer"
    MAW = "MAW"
    MENS_EN_MAATSCHAPPIJ = "Mens & Maatschappij"
    NASK_SCIENCE = "Nask/Science"
    NATUURKUNDE = "Natuurkunde"
    NEDERLANDS = "Nederlands"
    SCHEIKUNDE = "Scheikunde"
    SPAANS = "Spaans"
    WISKUNDE = "Wiskunde"
    WISKUNDE_A = "Wiskunde A"
    WISKUNDE_B = "Wiskunde B"
    UNKNOWN = "Unknown"


class SubjectCategory(str, Enum):
    TALEN = "Talen"
    EXACTE_VAKKEN = "Exacte vakken"
    MENS_EN_MAATSCHAPPIJ = "Mens- en maatschappijvakken"
    ECONOMIE = "Economie en bedrijf"


class Level(str, Enum):
    HAVO = "Havo"
    VWO = "Vwo"
    GYMNASIUM = "Gymnasium"
    VMBO_B = "Vmbo-b"   # basisberoepsgerichte leerweg
    VMBO_K = "Vmbo-k"   # kaderberoepsgerichte leerweg
    VMBO_G = "Vmbo-g"   # gemengde leerweg
    VMBO_T = "Vmbo-t"   # theoretische leerweg (mavo)
    UNKNOWN = "Unknown"


class SchoolYear(str, Enum):
    YEAR_1 = "1e jaar"
    YEAR_2 = "2e jaar"
    YEAR_3 = "3e jaar"
    YEAR_4 = "4e jaar"
    YEAR_5 = "5e jaar"
    YEAR_6 = "6e jaar"
    UNKNOWN = "Unknown"


class ClassDifficulty(str, Enum):
    """Verkeerslichtmodel voor klassenmoeilijkheid.

    Groen: goed hanteerbaar.
    Oranje: vraagt extra aandacht.
    Rood: uitdagend, intensieve begeleiding nodig.
    """

    GREEN = "Groen"
    ORANGE = "Oranje"
    RED = "Rood"


class ClassSupportChallenge(str, Enum):
    """Hoeveel ondersteuning of uitdaging de klas nodig heeft."""

    MORE_SUPPORT = "Meer ondersteuning"
    BALANCED = "Gebalanceerd"
    MORE_CHALLENGE = "Meer uitdaging"


class LesplanStatus(str, Enum):
    PENDING = "pending"
    GENERATING_OVERVIEW = "generating_overview"
    OVERVIEW_READY = "overview_ready"
    REVISING_OVERVIEW = "revising_overview"
    GENERATING_LESSONS = "generating_lessons"
    COMPLETED = "completed"
    FAILED = "failed"


class LessonPreparationStatus(str, Enum):
    PENDING = "pending"
    DONE = "done"


class UserRole(str, Enum):
    USER = "USER"
    ADMIN = "ADMIN"


class OrganizationRole(str, Enum):
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"


class InviteStatus(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
