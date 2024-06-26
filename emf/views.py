from django.db.models import Q
from django.http import Http404
from django.http import JsonResponse
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.conf import settings

from sqlalchemy.orm import joinedload
from sqlalchemy.orm import undefer
from sqlalchemy import func

from decimal import Decimal

import datetime

import emf.models

from .tilldb import tillsession, booziness, on_tap
from quicktill.models import RefusalsLog, StockType, Unit, Department, Payment


def current_time():
    # Override this when testing!
    # return datetime.datetime(2022, 6, 1, 17, 0, 0)
    return datetime.datetime.now()


def websocket_address(request):
    if settings.DEBUG:
        return "ws://localhost:8001/"
    return f"wss://{request.META['HTTP_HOST']}/websocket/"


class EventInfo:
    def __init__(self, now):
        # Work out how far through the event we are, based on the
        # supplied time.
        self.now = now
        sessions = emf.models.Session.objects.all()

        self.length = datetime.timedelta()
        self.total_consumption = 0.0
        self.time_passed = datetime.timedelta()
        self.expected_consumption = 0.0
        self.open = False
        self.next_open = None
        self.closes_at = None
        for s in sessions:
            start = s.opening_time
            end = s.closing_time
            weight = s.weight
            self.length += s.length
            self.total_consumption += weight
            if self.now >= end:
                # This segment has passed.
                self.time_passed += (end - start)
                self.expected_consumption += weight
            elif self.now >= start and self.now < end:
                # We are in this segment.
                self.open = True
                self.closes_at = end
                self.time_passed += (self.now - start)
                self.expected_consumption += weight * (
                    (self.now - start) / (end - start))
            elif self.now < start and not self.next_open:
                self.next_open = start
        if sessions:
            self.completed_fraction = self.time_passed / self.length
            self.completed_pct = self.completed_fraction * 100.0
            self.completed_pct_remainder = 100.0 - self.completed_pct
            self.expected_consumption_fraction = self.expected_consumption \
                / self.total_consumption
            self.expected_consumption_pct = self.expected_consumption_fraction \
                * 100.0
            self.expected_consumption_pct_remainder = 100.0 \
                - self.expected_consumption_pct
        else:
            self.completed_fraction = 0.0
            self.completed_pct = 0.0
            self.completed_pct_remainder = 100.0
            self.expected_consumption_fraction = 0.0
            self.expected_consumption_pct = 0.0
            self.expected_consumption_pct_remainder = 100.0


# We use this date format in templates - defined here so we don't have
# to keep repeating it.  It's available in templates as 'dtf'
dtf = "Y-m-d H:i"


@login_required
def refusals(request):
    with tillsession() as s:
        r = s.query(RefusalsLog)\
             .options(joinedload('user'))\
             .order_by(RefusalsLog.id)\
             .all()
        return render(
            request, 'emf/refusals.html',
            context={
                'refusals': r,
                'dtf': dtf,
            })


def display(request, page=None):
    return render(request, 'emf/display.html')


def display_info(request):
    now = current_time()

    # Work out whether we are open
    sessions = emf.models.Session.objects.filter(
        closing_time__gt=now)
    currently_open = False
    for s in sessions:
        if s.opening_time < now:
            currently_open = True

    # Fetch pages
    pages = emf.models.DisplayPage.objects.filter(
        Q(display_after=None) | Q(display_after__lt=now),
        Q(display_until=None) | Q(display_until__gt=now),
        enabled=True,
        condition__in=('A', 'O' if currently_open else 'C')).all()

    urgent = [p for p in pages if p.priority == 'U']

    if urgent:
        # The only pages are urgent pages
        pages = [p.as_dict() for p in urgent]
    else:
        pages = [p.as_dict() for p in pages]

    if not pages:
        # Display is blank!
        return JsonResponse({
            'name': 'blank',
            'header': ' ',
            'content': ' ',
            'duration': 5000 if settings.DEBUG else 30000,
            'page': 'Idle',
            'count': 0,
            'current': 0,
        })

    current = request.GET.get("current", "start")

    pagenum = 0
    for pn, p in enumerate(pages):
        if p['name'] == current:
            pagenum = pn + 1
            break

    if pagenum >= len(pages):
        pagenum = 0

    page = pages[pagenum]
    page['page'] = f"Page {pagenum + 1} of {len(pages)}" \
        if len(pages) > 1 else ""

    page['count'] = len(pages)
    page['current'] = pagenum

    if callable(page['content']):
        page['content'] = page['content']()

    page['duration'] = 5000 if settings.DEBUG else page['duration'] * 1000

    return JsonResponse(page)


def display_page_info(request, page):
    try:
        page = emf.models.DisplayPage.objects.get(slug=page)
    except emf.models.DisplayPage.DoesNotExist:
        raise Http404

    page = page.as_dict()
    if callable(page['content']):
        page['content'] = page['content']()
    page['duration'] = 5000
    page['page'] = "Page n of m"

    return JsonResponse(page)


def frontpage(request):
    try:
        page = emf.models.Page.objects.get(path='')
        content = page.as_html()
    except emf.models.Page.DoesNotExist:
        content = ''

    with tillsession() as s:
        info = EventInfo(current_time())

        alcohol_used, total_alcohol, alcohol_used_pct = booziness(s)

        ales, kegs, ciders = on_tap(s)

        sessions = emf.models.Session.objects.filter(
            closing_time__gt=current_time())

        return render(
            request, "emf/whatson.html",
            context={
                "info": info,
                "alcohol_used": alcohol_used,
                "total_alcohol": total_alcohol,
                "alcohol_used_pct": alcohol_used_pct,
                "alcohol_used_pct_remainder": 100.0 - alcohol_used_pct,
                "sessions": sessions,
                "session_comments_exist": any(s.comment for s in sessions),
                "ales": ales,
                "kegs": kegs,
                "ciders": ciders,
                "content": content,
            })


def pricelist(request):
    with tillsession() as s:
        products = s.query(StockType,
                           StockType.remaining / StockType.total * 100.0)\
            .join(Unit)\
            .join(Department)\
            .options(undefer('remaining'))\
            .order_by(Department.id, StockType.manufacturer, StockType.name)\
            .filter(StockType.remaining > 0.0)\
            .all()

        return render(
            request, "emf/pricelist.html",
            context={
                "products": products,
            })


def tapboard(request):
    return render(request, "emf/tapboard.html", context={
        "websocket_address": websocket_address(request),
    })


def tapboard_sw(request):
    # The service worker needs to be scoped to '/' to allow it to access
    # /static/whatever
    response = render(request, "emf/tapboard-sw.js",
                      content_type="text/javascript")
    response.headers['Service-Worker-Allowed'] = '/'
    return response


def cellarboard(request):
    return render(request, "emf/cellarboard.html", context={
        "websocket_address": websocket_address(request),
    })


def jontyfacts(request):
    from quicktill.models import StockItem, StockType, Unit, StockOut, User
    with tillsession() as s:
        pints_sold = s.query(func.sum(StockOut.qty)) \
            .select_from(StockOut)\
            .join(StockItem)\
            .join(StockType)\
            .join(Unit)\
            .filter(Unit.name == 'pint')\
            .filter(StockOut.removecode_id == 'sold')\
            .scalar()

        total_pints = s.query(func.sum(StockItem.size)) \
            .select_from(StockItem)\
            .join(StockType)\
            .join(Unit)\
            .filter(Unit.name == 'pint')\
            .scalar()

        volunteers = s.query(User).count()

        card_payments = s.query(Payment)\
            .filter(Payment.paytype_id == 'CARD')\
            .count()

        card_roll_used = card_payments * 0.12

        cash_payments = s.query(Payment)\
            .filter(Payment.paytype_id == 'CASH')\
            .filter(Payment.amount > Decimal("0.00"))\
            .count()

        club_mate = s.query(func.sum(StockItem.used))\
            .select_from(StockItem)\
            .join(StockType)\
            .filter(StockType.dept_id == 75)\
            .scalar()

        return render(request, "emf/jontyfacts.html",
                      {"pints_sold": pints_sold,
                       "total_pints": total_pints,
                       "volunteers": volunteers - 1,  # remove 1 for "shop"
                       "card_payments": card_payments,
                       "cash_payments": cash_payments,
                       "card_roll_used": card_roll_used,
                       "club_mate": club_mate,
                       })


# API views that do not access the till database
def api_sessions(request):
    sessions = emf.models.Session.objects.all()
    return JsonResponse({
        'sessions': [
            {k: getattr(s, k) for k in ('opening_time', 'closing_time')}
            for s in sessions],
        })


def api_progress(request):
    with tillsession() as s:
        alcohol_used, total_alcohol, alcohol_used_pct = booziness(s)
        info = EventInfo(current_time())

        return JsonResponse({
            'licensed_time_pct': info.completed_pct,
            'expected_consumption_pct': info.expected_consumption_pct,
            'actual_consumption_pct': (alcohol_used / total_alcohol) * 100,
        })
