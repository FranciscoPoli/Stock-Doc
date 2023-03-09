import yahoo_fin.stock_info as si
import streamlit as st
from streamlit_option_menu import option_menu
from streamlit_extras.colored_header import colored_header
import plotly.express as px
import pandas as pd
import json
import pyrebase


@st.cache_resource
def connect_db():
    key_dict = json.loads(st.secrets["textkey"])
    firebase = pyrebase.initialize_app(key_dict)
    db = firebase.database()

    return db


@st.cache_data(ttl=86400)
def get_data(ticker):
    db = connect_db()

    annual = db.child('year').child(ticker).get().val()
    dict_annual = {i: annual[i] for i in range(0, len(annual))}
    annual_json = json.dumps(dict_annual, indent=2)
    dfannual = pd.read_json(annual_json, orient="index").replace('None', pd.NA).fillna(0)
    dfannual['endDate'] = pd.to_datetime(dfannual['endDate']).dt.tz_localize(None)

    quarter = db.child('quarter').child(ticker).get().val()
    dict_quarter = {i: quarter[i] for i in range(0, len(quarter))}
    quarter_json = json.dumps(dict_quarter, indent=2)
    dfquarter = pd.read_json(quarter_json, orient="index").replace('None', pd.NA).fillna(0)
    dfquarter['endDate'] = pd.to_datetime(dfquarter['endDate']).dt.tz_localize(None)

    dfannual = dfannual.sort_values('endDate')
    dfquarter = dfquarter.sort_values('endDate')
    
    ticker_for_yahoo = ticker.replace('_', '-')
    stats = si.get_stats_valuation(ticker_for_yahoo).fillna("-")

    return [dfannual, dfquarter, stats]


@st.cache_data(ttl=86400)
def get_ticker_list():
    db = connect_db()
    reading = db.child('allnames').child('list').get().val()
    alltickers = list(reading['names'])
    tickerlist = ["", *alltickers]

    return tickerlist


@st.cache_data(ttl=28800)
def get_historical_prices(ticker):
    ticker_for_yahoo = ticker.replace('_', '-')
    prices = si.get_data(ticker_for_yahoo)['adjclose']

    return prices


def bar_graph(df, title):
    width = 450
    if title == 'Dividends per Share':
        width = 900

    colors = px.colors.qualitative.D3
    bar_chart = px.bar(
        df,
        color_discrete_sequence=colors,
        orientation='v',
        barmode='group',
        title=f'{title}',
        width=width,
        template='plotly_white')

    bar_chart.update_layout(plot_bgcolor='rgba(0,0,0,0)',
                            xaxis=dict(title=''),
                            yaxis=dict(title=''),
                            hoverlabel=dict(font=dict(color='white')),
                            bargroupgap=0.15,
                            bargap=0.25
                            )


    #bar_chart.update_traces(width=.4)
    #if not isinstance(df, pd.Series) and len(df.columns) >= 3:
    #    bar_chart.update_traces(width=.2)

    if title == 'Shares Outstanding':
        min = df.min()*0.95
        max = df.max()
        bar_chart.update_yaxes(range=[min, max])

    return bar_chart


st.set_page_config(page_title='Stock Doc', layout='wide')
hide_menu_style = """
        <style>
        #MainMenu {visibility: hidden;}
        </style>
        """
st.markdown(hide_menu_style, unsafe_allow_html=True)

ticker = ""

left_column, middle_column, right_column, right_column2, right_column3 = st.columns([1, 1, 0.2, 0.4, 0.4])

with left_column:
    # st.write('<style>div.row-widget.stRadio > div{flex-direction:row;}</style>', unsafe_allow_html=True)
    selection = st.radio("options", ['View Stock Fundamentals', 'Compare Stock Valuation metrics and Fundamentals'],
                         label_visibility='collapsed')

with middle_column:
    alltickers = get_ticker_list()
    if selection == "View Stock Fundamentals":
        ticker = st.selectbox("Choose Stock", sorted(alltickers))


    elif selection == "Compare Stock Valuation metrics and Fundamentals":
        multiselect = st.multiselect("Add Stocks to compare", sorted(alltickers))


colored_header(
    label="",
    description="",
    color_name="violet-70",
)
st.markdown(" ")

buffer1, buffer2, buffer31, buffer32 = st.columns([1, 1, 0.2, 0.8])

if ticker != "":
    with buffer2:
        toggle_bar = option_menu(
            menu_title=None,
            options=["Annual", "Quarter"],
            orientation="horizontal",
            styles={
                "container": {"padding": "0!important"},
                "nav-link": {
                    "font-size": "20px",
                    "margin": "0px",
                    "text-align": "center",
                    "--hover-color": "#bbb"},
                "nav-link-selected": {"font-weight": "bold"}
            }
        )


    try:
        db = connect_db()
        div = db.child('dividends').child(ticker).get().val()
        if div[0]['index'] == 'empty':
            dividends = pd.DataFrame()
        else:
            divdict = {i: div[i] for i in range(0, len(div))}

            dividends_json = json.dumps(divdict, indent=2)
            dividends = pd.read_json(dividends_json, orient="index").replace('None', pd.NA).fillna(0)
            dividends['index'] = pd.to_datetime(dividends['index']).dt.tz_localize(None)
            dividends = dividends.sort_values('index')
            
        annual, quarterly, stats = get_data(ticker)
        
    except Exception:
        st.warning("Stock is not in the database")
        st.stop()

    with buffer32:
        price_yesterday = get_historical_prices(ticker)[-2]
        price = si.get_live_price(ticker.replace('_', '-'))
        dif = price - price_yesterday
        st.metric("placeholder", f'{price.round(2)} USD', delta = f'{dif.round(2)} ({((dif/price_yesterday)*100).round(2)}%)',
                  label_visibility='collapsed')

    with right_column2:
        mkt_cap = price * quarterly.set_index('endDate')['commonStockSharesOutstanding'].astype(float)[-1]
        fcf = quarterly.set_index('endDate')['operatingCashflow'].astype(float).rolling(4).sum()[-1] - \
              quarterly.set_index('endDate')['capitalExpenditures'].astype(float).rolling(4).sum()[-1]
        price_to_FCF = (mkt_cap / fcf).round(2)
        earnings = quarterly.set_index('endDate')['netIncome'].astype(float).rolling(4).sum()[-1]
        roa = earnings / quarterly.set_index('endDate')['totalAssets'].astype(float)[-1]
        st.write(f'Market Cap:  {stats.iloc[0,1]}')
        st.write(f'PEG Ratio:  {stats.iloc[4,1]}')
        st.write(f'ROA:  {(roa*100).round(2)}%')
        st.write(f'Price to FCF:  {price_to_FCF}')

    with right_column3:
        cashflowyield = ((fcf / mkt_cap)*100).round(2)
        roe = earnings / quarterly.set_index('endDate')['totalShareholderEquity'].astype(float)[-1]
        st.write(f'Trailing P/E:  {(mkt_cap/earnings).round(2)}')
        st.write(f'Forward P/E:  {stats.iloc[3,1]}')
        st.write(f'ROE:  {(roe * 100).round(2)}%')
        st.write(f'Cash flow yield:  {cashflowyield}%')

    if toggle_bar == 'Annual':
        db_financials = annual
        db_financials['endDateplaceholder'] = db_financials['endDate']
        db_financials['endDate'] = db_financials['endDate'].dt.year
        quarter = False

    else:
        db_financials = quarterly
        db_financials['endDate'] = db_financials['endDate'].dt.to_period('Q')
        quarter = True


    columna, columnb, columnc = st.columns(3)
    with columna:
        start, end = st.select_slider("Change date range", options=db_financials['endDate'],
                                      value=(list(db_financials['endDate'])[0], list(db_financials['endDate'])[-1])
                                      )

        db_financials = db_financials[(db_financials.endDate >= start) & (db_financials.endDate <= end)]

        if not quarter:
            db_financials['endDate'] = pd.to_datetime(db_financials['endDateplaceholder']).dt.strftime('%Y')
        else:
            db_financials['endDate'] = db_financials['endDate'].dt.strftime('Q%q %Y')

        db_financials = db_financials.set_index('endDate').transpose()

    # container.title(f'{price:.2f}')

    revenues = db_financials.loc[['totalRevenue', 'netIncome']].astype(float).transpose()
    revenues = revenues.reset_index().rename(columns={"totalRevenue": "Revenue", "netIncome": "Income"}) \
        .set_index('endDate')

    rev_pctchange = (db_financials.loc['totalRevenue'].astype(float).pct_change()) * 100
    rev_pctchange = rev_pctchange.rename("Growth %")


    sharesoutstanding = db_financials.loc['commonStockSharesOutstanding'].astype(float)
    sharesoutstanding = sharesoutstanding.rename("Shares")


    if (db_financials.loc['longTermDebtNoncurrent'] == 0).all():
        db_financials.loc['longTermDebtNoncurrent'] = db_financials.loc['longTermDebt']
    cash_debt = db_financials.loc[['cashAndShortTermInvestments', 'longTermDebtNoncurrent']].astype(float).transpose()
    cash_debt = cash_debt.reset_index().rename(columns={"cashAndShortTermInvestments":"Cash", "longTermDebtNoncurrent":"Debt"})\
        .set_index('endDate')

    capex = db_financials.loc['capitalExpenditures'].astype(float)
    capex = capex.rename("CAPEX")

    free_cash_flow = db_financials.loc['operatingCashflow'].astype(float)
    free_cash_flow2 = pd.concat([free_cash_flow, capex.reindex(free_cash_flow.index)], axis=1)
    free_cash_flow2['FCF'] = free_cash_flow2['operatingCashflow'] - free_cash_flow2['CAPEX']
    free_cash_flow2 = free_cash_flow2['FCF']

    margins = db_financials.loc[['totalRevenue', 'operatingIncome', 'grossProfit', 'netIncome']].astype(float).transpose()
    margins['Gross Margin'] = (margins['grossProfit'] / margins['totalRevenue']) * 100
    margins['Net Margin'] = (margins['netIncome'] / margins['totalRevenue']) * 100
    # margins['Operating Margin'] = (margins['operatingIncome'] / margins['totalRevenue']) * 100
    margins = margins.drop('totalRevenue', axis=1).drop('operatingIncome', axis=1)\
        .drop('grossProfit', axis=1).drop('netIncome', axis=1)
    
    ebitda = db_financials.loc[['operatingIncome', 'depreciationDepletionAndAmortization']].astype(float).transpose()
    ebitda['EBITDA'] = ebitda['operatingIncome'] + ebitda['depreciationDepletionAndAmortization']
    ebitda = ebitda['EBITDA']

    ebit = db_financials.loc['operatingIncome'].astype(float)
    ebit = ebit.rename('EBIT')
    
    interest = db_financials.loc['interestExpense'].astype(float)
    interest = interest.rename('Interest')
    
    fcf = pd.concat([ebitda.reindex(ebit.index), ebit, free_cash_flow2.reindex(ebit.index), interest.reindex(ebit.index)], axis=1)

    dividends_annual = pd.DataFrame()

    col11, col12, col13 = st.columns([1, 1, 1])

    with col11:
        st.plotly_chart(bar_graph(revenues, 'Revenue and Net Income'))
        st.plotly_chart(bar_graph(rev_pctchange, 'Revenue growth %'))
        st.plotly_chart(bar_graph(sharesoutstanding, 'Shares Outstanding'))

    with col12:
        st.plotly_chart(bar_graph(margins, 'Gross and Net Margin %'))
        st.plotly_chart(bar_graph(fcf, 'EBITDA, EBIT, FCF vs Interest Expense'))
        if quarter and dividends.empty is False:
            dividends['index'] = pd.to_datetime(dividends['index']).dt.to_period('Q').dt.strftime('Q%q %Y')
            dividend_quarter = dividends.drop('ticker', axis=1).set_index('index')
            st.plotly_chart(bar_graph(dividend_quarter, 'Dividends per Share'))


        elif dividends.empty is True:
            st.subheader('Company pays no dividends')

        else:
            dividends_annual = dividends
            dividends_annual['index'] = pd.to_datetime(dividends_annual['index']).dt.strftime('%Y')
            dividends_annual = dividends_annual.groupby(['index']).sum(numeric_only=True)
            st.plotly_chart(bar_graph(dividends_annual, 'Dividends per Share'))



    with col13:
        st.plotly_chart(bar_graph(cash_debt, 'Cash vs Long Debt'))
        st.plotly_chart(bar_graph(capex, 'CAPEX'))
        if dividends.empty is False:
            dividend_quarter = dividends.drop('ticker', axis=1).set_index('index')
            divyield = dividend_quarter['dividend'].astype(float).rolling(4).sum()[-1] / price
            payoutratio = quarterly.set_index('endDate')['dividendPayout'].astype(float).rolling(4).sum()[-1] / \
                          quarterly.set_index('endDate')['netIncome'].astype(float).rolling(4).sum()[-1]
            st.write(f'Dividend Yield:  {(divyield * 100).round(2)}%')
            st.write(f'Payout Ratio:  {(payoutratio * 100).round(2)}%')



elif selection == "Compare Stock Valuation metrics and Fundamentals" and multiselect:
    final = pd.DataFrame()
    tickers = multiselect

    tab1, tab2 = st.tabs(["Stock Fundamentals", "Stock Valuation Metrics"])
    with tab1:
        col1, col2, col3 = st.columns(3)
        with col2:
            st.markdown("")
            toggle_bar = option_menu(
                menu_title=None,
                options=["Annual", "Quarter"],
                orientation="horizontal",
                styles={
                    "container": {"padding": "0!important"},
                    "nav-link": {
                        "font-size": "20px",
                        "margin": "0px",
                        "text-align": "center",
                        "--hover-color": "#bbb"},
                    "nav-link-selected": {"font-weight": "bold"}
                }
            )

        finalrevenue = pd.DataFrame()
        finalrevenuepct = pd.DataFrame()
        finalnetincome = pd.DataFrame()
        finalmargins = pd.DataFrame()
        finalgrossmargins = pd.DataFrame()
        finalcash = pd.DataFrame()
        finalcapex = pd.DataFrame()
        finalfcf = pd.DataFrame()
        finaldebt = pd.DataFrame()
        finalebitda = pd.DataFrame()
        finalebit = pd.DataFrame()

        start = ''
        end = ''
        for ticker in tickers:
            try:
                annual, quarterly, _ = get_data(ticker)
            except:
                st.warning("Stock is not in the database")
                st.stop()

            if toggle_bar == 'Annual':
                db_financials = annual
                db_financials['endDateplaceholder'] = db_financials['endDate']
                db_financials['endDate'] = db_financials['endDate'].dt.year
                quarter = False

            else:
                db_financials = quarterly
                db_financials['endDate'] = db_financials['endDate'].dt.to_period('Q')
                quarter = True

            if not start and not end:
                columna2, columnb2, columnc2 = st.columns(3)
                with columna2:
                    st.markdown(" ")
                    db_financials = db_financials.reset_index()
                    start, end = st.select_slider("Change date range", options=db_financials['endDate'],
                                                  value=(
                                                  list(db_financials['endDate'])[0], list(db_financials['endDate'])[-1]),
                                                  )

            db_financials = db_financials[(db_financials.endDate >= start) & (db_financials.endDate <= end)]

            if not quarter:
                db_financials['endDate'] = pd.to_datetime(db_financials['endDateplaceholder']).dt.strftime('%Y')
            else:
                db_financials['endDate'] = db_financials['endDate'].dt.strftime('Q%q %Y')

            db_financials = db_financials.set_index('endDate').transpose()

            revenue = db_financials.loc['totalRevenue'].astype(float)
            # revenue = revenue.reset_index().rename(columns={revenue.name: ticker}).set_index('endDate')
            revenue = revenue.rename(ticker)
            finalrevenue[ticker] = revenue

            rev_pctchange = (db_financials.loc['totalRevenue'].astype(float).pct_change()) * 100
            rev_pctchange = rev_pctchange.rename(ticker)
            finalrevenuepct[ticker] = rev_pctchange

            netincome = db_financials.loc['netIncome'].astype(float)
            netincome = netincome.rename(ticker)
            finalnetincome[ticker] = netincome

            netmargins = db_financials.loc[['totalRevenue', 'netIncome']].astype(float).transpose()
            netmargins[ticker] = (netmargins['netIncome'] / netmargins['totalRevenue']) * 100
            netmargins = netmargins[ticker].astype(float)
            finalmargins[ticker] = netmargins

            grossmargins = db_financials.loc[['totalRevenue', 'grossProfit']].astype(float).transpose()
            grossmargins[ticker] = (grossmargins['grossProfit'] / grossmargins['totalRevenue']) * 100
            grossmargins = grossmargins[ticker].astype(float)
            finalgrossmargins[ticker] = grossmargins

            cash = db_financials.loc['cashAndShortTermInvestments'].astype(float)
            cash = cash.rename(ticker)
            finalcash[ticker] = cash

            capex = db_financials.loc['capitalExpenditures'].astype(float)
            capex = capex.rename(ticker)
            finalcapex[ticker] = capex

            free_cash_flow = db_financials.loc['operatingCashflow'].astype(float)
            free_cash_flow = pd.concat([free_cash_flow, capex.reindex(free_cash_flow.index)], axis=1)
            free_cash_flow[ticker] = free_cash_flow['operatingCashflow'] - free_cash_flow[ticker]
            free_cash_flow = free_cash_flow[ticker].astype(float)
            finalfcf[ticker] = free_cash_flow

            if (db_financials.loc['longTermDebtNoncurrent'] == 0).all():
                db_financials.loc['longTermDebtNoncurrent'] = db_financials.loc['longTermDebt']
            debt = db_financials.loc['longTermDebtNoncurrent'].astype(float)
            debt = debt.rename(ticker)
            finaldebt[ticker] = debt
            
            ebitda = db_financials.loc[['operatingIncome', 'depreciationDepletionAndAmortization']].astype(float).transpose()
            ebitda[ticker] = ebitda['operatingIncome'] + ebitda['depreciationDepletionAndAmortization']
            ebitda = ebitda[ticker].astype(float)
            finalebitda[ticker] = ebitda
            
            ebit = db_financials.loc['operatingIncome'].astype(float)
            ebit = ebit.rename(ticker)
            finalebit[ticker] = ebit


        col11, col12, col13 = st.columns([1, 1, 1])

        with col11:
            st.plotly_chart(bar_graph(finalrevenue, 'Revenue'))
            st.plotly_chart(bar_graph(finalgrossmargins, 'Gross Margins %'))
            st.plotly_chart(bar_graph(finalcash, 'Cash'))
            st.plotly_chart(bar_graph(finalebitda, 'EBITDA'))

        with col12:
            st.plotly_chart(bar_graph(finalnetincome, 'Net Income'))
            st.plotly_chart(bar_graph(finalmargins, 'Net Margins %'))
            st.plotly_chart(bar_graph(finaldebt, 'Long Debt'))
            st.plotly_chart(bar_graph(finalebit, 'EBIT'))

        with col13:
            st.plotly_chart(bar_graph(finalfcf, 'FCF'))
            st.plotly_chart(bar_graph(finalrevenuepct, 'Revenue Growth %'))
            st.plotly_chart(bar_graph(finalcapex, 'CAPEX'))


    with tab2:
        cola1, colb1, colc1 = st.columns(3)
        with colb1:
            metrics = ["Price to Earnings (P/E)", "Price to Free Cash Flow (P/FCF)", "Price to Operating Cash Flow (P/OCF)", 
                       "Price to EBITDA (P/EBITDA)", "Price to Earnings Before Tax (P/EBT)", "Price to Sales (P/S)"]
            dropdown = st.selectbox("Select Valuation metric", metrics)

        # date_tickers = []
        # for ticker in tickers:
        #     min_date = pd.read_sql(ticker, annualengine).replace('None', pd.NA).fillna(0)['endDate'].min()
        #     date_tickers.append([min_date, ticker])

        for ticker in tickers:
            annual, quarter, _ = get_data(ticker)
            annual = annual.set_index('endDate')
            quarter = quarter.set_index('endDate')


            df = quarter['commonStockSharesOutstanding'].astype(float)
            today = pd.to_datetime('today')
            df[today] = df[-1]
            df = df.reset_index()
            df['division'] = df['commonStockSharesOutstanding'].div(df['commonStockSharesOutstanding'].shift(1))
            df['division'] = df['division'].shift(-1).fillna(1)
            df.loc[df["division"] < 1.5, "division"] = pd.NA
            df = df.bfill().fillna(1)
            df['commonStockSharesOutstanding'] = df['commonStockSharesOutstanding'] * df['division']
            df = df.set_index('endDate')['commonStockSharesOutstanding']
            df = df.asfreq('D', method='ffill')  # .interpolate(method='values', limit_direction='forward')

            if dropdown == "Price to Free Cash Flow (P/FCF)":
                fcf = quarter.loc[:, ['capitalExpenditures', 'operatingCashflow']].astype(float)
                fcf['Metric'] = fcf['operatingCashflow'] - fcf['capitalExpenditures']
                fcf = fcf['Metric'].rolling(4).sum(numeric_only=True)
                fcf[today] = fcf[-1]
                if (fcf.values < 0).any():
                    valuation = fcf.asfreq('D', method='ffill')
                else:
                    valuation = fcf.asfreq('D').interpolate(method='linear', limit_direction='forward')

            elif dropdown == "Price to Sales (P/S)":
                revenue = quarter['totalRevenue'].astype(float).rolling(4).sum()
                revenue[today] = revenue[-1]
                revenue = revenue.reset_index().rename(columns={"totalRevenue": "Metric"}).set_index('endDate')
                if (revenue.values < 0).any():
                    valuation = revenue.asfreq('D', method='ffill')
                else:
                    valuation = revenue.asfreq('D').interpolate(method='linear', limit_direction='forward')

            elif dropdown == "Price to Earnings (P/E)":
                income = quarter['netIncome'].astype(float).rolling(4).sum()
                income[today] = income[-1]
                income = income.reset_index().rename(columns={"netIncome": "Metric"}).set_index('endDate')
                if (income.values < 0).any():
                    valuation = income.asfreq('D', method='ffill')
                else:
                    valuation = income.asfreq('D').interpolate(method='linear', limit_direction='forward')
            
            elif dropdown == "Price to Operating Cash Flow (P/OCF)":
                ocf = quarter['operatingCashflow'].astype(float).rolling(4).sum()
                ocf[today] = ocf[-1]
                ocf = ocf.reset_index().rename(columns={"operatingCashflow": "Metric"}).set_index('endDate')
                if (ocf.values < 0).any():
                    valuation = ocf.asfreq('D', method='ffill')
                else:
                    valuation = ocf.asfreq('D').interpolate(method='linear', limit_direction='forward')
                    
            elif dropdown == "Price to EBITDA (P/EBITDA)":
                ebitda1 = quarter.loc[:, ['operatingIncome', 'depreciationDepletionAndAmortization']].astype(float)
                ebitda1['Metric'] = ebitda1['operatingIncome'] + ebitda1['depreciationDepletionAndAmortization']
                ebitda1 = ebitda1['Metric'].rolling(4).sum(numeric_only=True)
                ebitda1[today] = ebitda1[-1]
                if (ebitda1.values < 0).any():
                    valuation = ebitda1.asfreq('D', method='ffill')
                else:
                    valuation = ebitda1.asfreq('D').interpolate(method='linear', limit_direction='forward')
                    
            elif dropdown == "Price to Earnings Before Tax (P/EBT)":
                ebt = quarter['incomeBeforeTax'].astype(float).rolling(4).sum()
                ebt[today] = ebt[-1]
                ebt = ebt.reset_index().rename(columns={"incomeBeforeTax": "Metric"}).set_index('endDate')
                if (ebt.values < 0).any():
                    valuation = ebt.asfreq('D', method='ffill')
                else:
                    valuation = ebt.asfreq('D').interpolate(method='linear', limit_direction='forward')

            stockprice = get_historical_prices(ticker)

            result = pd.concat([df, valuation, stockprice.reindex(df.index)], axis=1).dropna()
            result['Mkt Cap'] = result['adjclose'] * result['commonStockSharesOutstanding']
            result[ticker] = result['Mkt Cap'] / result['Metric']
            result = result[ticker].dropna()

            final[ticker] = result


        columna, columnb, columnc = st.columns([0.04, 1.1, 0.14])
        with columnb:
            st.markdown("")
            final = final.reset_index()
            final['endDate'] = final['endDate'].dt.date
            start, end = st.select_slider("dummyname3", options=final['endDate'],
                                          value=(list(final['endDate'])[0], list(final['endDate'])[-1]),
                                          label_visibility='collapsed')

            final = final[(final.endDate >= start) & (final.endDate <= end)]
            final = final.set_index('endDate')

        colors = px.colors.qualitative.D3
        linegraph = px.line(final, template='plotly_dark', color_discrete_sequence=colors)

        linegraph.update_traces(line=dict(width=2))
        for i, d in enumerate(linegraph.data):
            linegraph.add_scatter(x=[d.x[-1]], y=[d.y[-1]],
                                  mode='markers+text',
                                  text=f"{d.y[-1].round(2)} {d.name}",
                                  textfont=dict(color=d.line.color),
                                  textposition='middle right',
                                  marker=dict(color=d.line.color, size=12),
                                  # legendgroup=d.name,
                                  showlegend=False)

        linegraph.update_layout(plot_bgcolor='rgba(0,0,0,0)',
                                xaxis=dict(title=''),
                                yaxis=dict(title=''),
                                hoverlabel=dict(font=dict(color='white')),
                                width=1200,
                                height=500,
                                showlegend=False
                                )
        st.plotly_chart(linegraph)
