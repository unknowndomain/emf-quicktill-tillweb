# Display screens for the bar
from django.template.loader import render_to_string
from quicktill.models import *
from .tilldb import *

displays = {}


class display_meta(type):
    def __init__(cls, name, bases, attrs):
        displays[name] = cls


class Display(metaclass=display_meta):
    description = "Blank display"

    def __init__(self, s):
        self.text = ""


class OnTap(Display):
    description = "Drinks on tap"

    def __init__(self, s):
        ales, kegs, ciders = on_tap(s)

        self.text = render_to_string(
            'emf/display-on-tap.html',
            context={'ales': ales, 'kegs': kegs, 'ciders': ciders})


class CansAndBottles(Display):
    description = "Craft cans and bottles"

    def __init__(self, s):
        r = s.query(StockType)\
             .join(Unit)\
             .filter(StockType.dept_id.in_([60, 62, 64, 66]))\
             .filter(StockType.remaining > 0.0)\
             .filter(StockType.abv != None)\
             .options(undefer('remaining'))\
             .order_by(StockType.manufacturer, StockType.name)\
             .all()

        self.text = render_to_string(
            'emf/display-cans-and-bottles.html',
            context={'types': r,
                     'num_types': len(r),
            })


class Wines(Display):
    description = "Wines and wine cans"

    def __init__(self, s):
        wines = s.query(StockType,
                        func.round(StockType.saleprice / (750/125), 1),
                        func.round(StockType.saleprice / (750/175), 1),
                        func.round(StockType.saleprice / (750/250), 1))\
                 .filter(StockType.dept_id == 90)\
                 .filter(StockType.remaining > 0.0)\
                 .order_by(StockType.manufacturer, StockType.name)\
                 .all()

        cans = s.query(StockType)\
                .join(Unit)\
                .filter(StockType.dept_id == 95)\
                .filter(StockType.remaining > 0.0)\
                .filter(StockType.abv != None)\
                .options(undefer('remaining'))\
                .order_by(StockType.manufacturer, StockType.name)\
                .all()

        self.text = render_to_string(
            'emf/display-wines.html',
            context={'wines': wines, 'cans': cans})


# Not used in 2022
class WinesAndSpirits(Display):
    description = "Wines and spirits"

    def __init__(self, s):
        wines = s.query(StockType,
                        func.round(StockType.saleprice / (750/125), 1),
                        func.round(StockType.saleprice / (750/175), 1),
                        func.round(StockType.saleprice / (750/250), 1))\
                 .filter(StockType.dept_id == 90)\
                 .filter(StockType.remaining > 0.0)\
                 .order_by(StockType.manufacturer, StockType.name)\
                 .all()

        # XXX list wine cans here? Dept 95 for those

        # We want all stocktypes with dept 4, but only
        # if there are >0 qty remaining
        spirits = s.query(StockType)\
                   .filter(StockType.dept_id == 40)\
                   .filter(StockType.remaining > 0.0)\
                   .options(undefer('remaining'))\
                   .order_by(StockType.manufacturer, StockType.name)\
                   .all()

        self.text = render_to_string(
            'emf/display-wines-and-spirits.html',
            context={'wines': wines, 'spirits': spirits})


class SpiritsAndMixers(Display):
    description = "Spirits and mixers"

    def __init__(self, s):
        spirits = s.query(StockType)\
                   .filter(StockType.dept_id == 40)\
                   .filter(StockType.remaining > 0.0)\
                   .options(undefer('remaining'))\
                   .order_by(StockType.manufacturer, StockType.name)\
                   .all()

        soft = s.query(StockType, StockType.remaining / StockType.total * 100.0)\
                .filter(StockType.dept_id == 70)\
                .filter(StockType.remaining > 0.0)\
                .options(undefer('remaining'))\
                .order_by(StockType.manufacturer, StockType.name)\
                .all()

        self.text = render_to_string(
            'emf/display-spirits-and-mixers.html',
            context={'spirits': spirits,
                     'soft': soft,
                     'num_items': len(spirits) + len(soft),
            })


class ClubMate(Display):
    description = "Club Mate"

    def __init__(self, s):
        mate = s.query(StockType, StockType.remaining, StockType.total,
                       StockType.remaining / StockType.total * 100.0)\
                .filter(StockType.manufacturer == "Club Mate")\
                .order_by(desc(StockType.name))\
                .all()

        self.text = render_to_string(
            'emf/display-club-mate.html',
            context={'mate': mate})


class SoftDrinks(Display):
    description = "Soft drinks"

    def __init__(self, s):
        soft = s.query(StockType, StockType.remaining / StockType.total * 100.0)\
                .filter(StockType.dept_id == 70)\
                .filter(StockType.remaining > 0.0)\
                .options(undefer('remaining'))\
                .order_by(StockType.manufacturer, StockType.name)\
                .all()

        self.text = render_to_string(
            'emf/display-soft-drinks.html',
            context={'soft': soft})


class Progress(Display):
    description = "Event progress"

    def __init__(self, s):
        alcohol_used, total_alcohol, alcohol_used_pct = booziness(s)
        from .views import EventInfo, current_time
        info = EventInfo(current_time())

        self.text = render_to_string(
            'emf/display-progress.html',
            context={
                'info': info, 'alcohol_used': alcohol_used,
                'total_alcohol': total_alcohol,
                'alcohol_used_pct': alcohol_used_pct,
                'alcohol_used_pct_remainder': 100.0 - alcohol_used_pct,
            })


class OpeningTimes(Display):
    description = "Bar opening times"

    def __init__(self, s):
        # Override quicktill.models.Session
        from .models import Session
        from .views import current_time
        sessions = Session.objects.filter(closing_time__gt=current_time())

        self.text = render_to_string(
            'emf/display-sessions.html',
            context={
                'sessions': sessions,
            })