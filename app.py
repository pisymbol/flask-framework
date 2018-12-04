# The Data Incubator: 12-Day Program
#
# Day 10 Milestone: Stock Data Lookup Demo
#
# Author: Alexander Sack

import feedparser
import io
import os
import pandas as pd
import re
import requests
import urllib

from bokeh.embed import components
from bokeh.models import ColumnDataSource, HoverTool, NumeralTickFormatter
from bokeh.plotting import figure
from bokeh.resources import INLINE
from bokeh.util.string import encode_utf8

from flask import Flask, render_template, request, redirect, flash, url_for, Markup

# Quandl is no longer maintaining any up to free date datasets.
# Use Alpha Vantage instead which is updated daily. We also get
# the ability to download in CSV format which makes importimg into
# pandas easier.
ALPHA_VANTAGE_KEY = 'EHXSSM9A86COI0Z3'
AV_API_URL = 'https://www.alphavantage.co/query?function={0}&symbol={1}&outputsize={2}&datatype={3}&apikey=' + ALPHA_VANTAGE_KEY

# Yahoo Finance! APIs 
YAHOO_FINANCE_API_URL = 'http://d.yimg.com/autoc.finance.yahoo.com/autoc?query={}&region=1&lang=en'
YAHOO_FINANCE_RSS_URL = 'http://finance.yahoo.com/rss/headline?s={0}'

# Nasdaq keeps a fairly up to date list of all major stock tickers
NASDAQ_SYMBOL_FTP = 'ftp://ftp.nasdaqtrader.com/SymbolDirectory/'
NASDAQ_OTHER = 'otherlisted.txt'
NASDAQ_LISTED = 'nasdaqlisted.txt'

# Global list of ticker symbols
TICKERS = []

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'tdi')

def ticker2name(ticker):
    """ Convert ticker to company name using Yahoo! Finance API """

    url = "http://d.yimg.com/autoc.finance.yahoo.com/autoc?query={}&region=1&lang=en".format(ticker)
    r = requests.get(url)
    if r.status_code == 200:
        js = r.json()
        result = js['ResultSet']['Result'][0]
        if result['symbol'] == ticker:
            return result['name']
    return ""

def get_news(ticker):
    """ Get recent headlines from Yahoo! Finance RSS Feed """

    # Again, getting the ticker's latest news is optional and thus non-fatal
    # if the RSS feed is down for whatever reason.
    try:
        feed = feedparser.parse(YAHOO_FINANCE_RSS_URL.format(ticker))
        return feed['entries']
    except:
        pass

def alpha_vantage(ticker, function='TIME_SERIES_DAILY', outputsize='compact', datatype='csv'):
    """
    Fetch stock data from Alpha Vantage API

    FIXME: We should probably cache the data to make response time
    faster but for now we fetch directly from their web API on every
    form submit. Boo!
    """

    df = None
    r = requests.get(AV_API_URL.format(function, ticker, outputsize, datatype))
    if r.status_code == 200:
        # AV has a weird thing that if you ask for an invalid ticker, the RPC
        # still returns 200! So we check if 'Error Message' is in the text to
        # indicate something bad happened.
        if re.search(r'Error Message', r.text):
            return df

        # Have a CSV, read in as a dataframe
        sio = io.StringIO(r.text)
        if datatype == 'csv':
            df = pd.read_csv(sio)
        df['timestamp'] = pd.to_datetime(df['timestamp'])

    return df

def create_figure(df, ticker, lines):
    """ Create Bokeh figure """

    plot_script = ""
    plot_div = ""

    # Various figure mappings
    line_map = {
            'open' : {'color' : 'blue', 'legend' : 'Open'},
            'close' : { 'color': 'red', 'legend' : 'Adj Close'},
            'high' : { 'color' : 'orange', 'legend' : 'High'},
            'low' : { 'color' : 'black', 'legend' : 'Low'},
    }

    name = ticker2name(ticker)
    title = ticker + ' (' + name + ') '
    source = ColumnDataSource(df)
    hoverTools = []
    p = figure(plot_width=800, plot_height=300, x_axis_type="datetime", title=title)

    # Based on what the user requested build lines and hovertools
    for line in lines:
        if line in df:
            p.line(x='timestamp', y=line, source=source,
                    legend=line_map[line]['legend'], color=line_map[line]['color'])
            hoverTools.append((line_map[line]['legend'], '@' + line))
    p.add_tools(HoverTool(tooltips=hoverTools))
    p.yaxis[0].formatter = NumeralTickFormatter(format="$0.00")
    p.grid.grid_line_color = None

    # Return the HTML components needed to embed in our template.
    script, div = components(p)

    return script, div

@app.route('/', methods=['GET', 'POST'])
def index():
    # Static resources
    js_resources = INLINE.render_js()
    css_resources = INLINE.render_css()
    plot_script = ""
    plot_div = ""
    articles = ""

    # Parse form data
    if request.method == 'POST':
        ticker = request.form.get('ticker').strip().upper()
        close = request.form.get('close')
        opening = request.form.get('open')
        high = request.form.get('high')
        low = request.form.get('low')

        # Go get stock info
        df = alpha_vantage(ticker)
        if df is not None:
            plot_script, plot_div = create_figure(df, ticker, [opening, close, high, low])
            articles = get_news(ticker)
        else:
            flash('Stock ticker not found.')
            return redirect(url_for('index'))

    # Render our results (if any)
    html = render_template('index.html', js_resources=js_resources, css_resources=css_resources,
            plot_script=plot_script, plot_div=plot_div, articles=articles, entries=TICKERS)

    return encode_utf8(html)

@app.route('/about')
def about():
  return render_template('about.html')

def tickers_init():
    """ Dynamically build a stock ticker catalog """

    # NOTE: Failure is perfeclty fine. This is strictly for convenience.
    for txt in [NASDAQ_LISTED, NASDAQ_OTHER]:
        try:
            file_txt, headers = urllib.request.urlretrieve(NASDAQ_SYMBOL_FTP + '/' + txt)
            if file_txt:
                with open(file_txt, 'r') as f:
                    # Last line is just a useless 'File Creation' entry
                    for line in f.readlines()[:-1]:
                        TICKERS.append(line.split('|')[0].strip())
                os.unlink(file_txt)
        except:
            pass

    if TICKERS:
        sorted(TICKERS)

if __name__ == '__main__':
    tickers_init()

    # FIXME: Move to separate settings file.
    app.run(port=33507, debug=True) # Heroku reserved port for flask applications
