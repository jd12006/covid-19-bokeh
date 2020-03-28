# run app in terminal using command bokeh serve --show covid_app.py

import glob
import pandas as pd
import os
import geopandas as gpd
import json 
import datetime
import itertools
from bokeh.io import output_notebook, show, output_file, curdoc
from bokeh.plotting import figure, ColumnDataSource
from bokeh.models import GeoJSONDataSource, LinearColorMapper, ColorBar
from bokeh.palettes import brewer 
from bokeh.models import DateSlider, Select, HoverTool
from bokeh.layouts import widgetbox, row, column
from bokeh.models.widgets import Panel, Tabs


PATH = '/Users/jdorni/Documents/training/COVID-19'

def prepare_data(df, metric):
    
    # organise cols
    
    df.rename({'Country/Region': 'country', 'Province/State': 'province'}, axis=1, inplace=True)
    df.columns = [x.lower() for x in df.columns]
    df.fillna('No data', inplace=True)
    
    # convert from wide to long 
    # to get one row per province/country/date

    df = pd.melt(df, id_vars=['country', 'province', 'lat', 'long'],
                 var_name='day', value_name=metric)

    df.set_index(['country', 'province', 'lat', 'long', 'day'], inplace=True)
    
    return df.sort_values(by=['country', 'province'])


# def prepare_geojsondata(df):
#     """Convert GeoDataFrame to GeoJSON format so it can be read by Bokeh 
#     (ColumnDataSource can't contain the multipolygons dtypes required for mapping)
#     (for mapping, Bokeh consumes GeoJSON format which represents geographical features with JSON)
#     """
#     # Read data to json.
#     df_json = json.loads(df.to_json())

#     # Convert to String like object.
#     json_data = json.dumps(df_json)
    
#     # Convert JSON to GeoDataSource to be read by Bokeh
#     geosource = GeoJSONDataSource(geojson=json_data)
    
#     return geosource

def source_by_date(data, selected_day):
    """Create geosource for date selected by user on slider. Returns pd.DataFrame."""
    selected_day = selected_day.strftime('%Y-%m-%d')
    new_data = data.loc[data['day'] == selected_day] 
    return new_data


## import data

confirmed = pd.read_csv(f'{PATH}/csse_covid_19_data/csse_covid_19_time_series/time_series_covid19_confirmed_global.csv')
deaths = pd.read_csv(f'{PATH}/csse_covid_19_data/csse_covid_19_time_series/time_series_covid19_deaths_global.csv')
recovered = pd.read_csv(f'{PATH}/csse_covid_19_data/csse_covid_19_time_series/time_series_covid19_recovered_global.csv')

# read in shapefile using Geopandas
shapefile = f'{PATH}/country_boundaries/ne_110m_admin_0_countries/ne_110m_admin_0_countries.shp'
gdf = gpd.read_file(shapefile)[['ADMIN', 'ADM0_A3', 'geometry']]


## prepare data

# rename columns
gdf.columns = ['country', 'country_code', 'geometry']

confirmed_melted = prepare_data(df=confirmed, metric='confirmed')
deaths_melted = prepare_data(df=deaths, metric='deaths')
recovered_melted = prepare_data(df=recovered, metric='recovered')

df = pd.concat([confirmed_melted, deaths_melted, recovered_melted], axis=1)
df.reset_index(inplace=True)


# sum provinces to get totals by whole countries  
df = df.groupby(['country', 'day']).agg(
    confirmed=pd.NamedAgg(column='confirmed', aggfunc='sum'),
    deaths=pd.NamedAgg(column='deaths', aggfunc='sum'),
    recovered=pd.NamedAgg(column='recovered', aggfunc='sum'))

df = df.reset_index()

# convert date to a sortable string format
df['day'] = pd.to_datetime(df['day']).dt.strftime("%Y-%m-%d")


# keep record of original country name
df['country_original'] = df['country']

# remap country names (need to sum again after this as some countries are combined)

country_map = {
    'Congo (Kinshasa)': 'Democratic Republic of the Congo',
    'Congo (Brazzaville)': 'Democratic Republic of the Congo',
    "Cote d'Ivoire": 'Ivory Coast',
    'Eswatini': 'eSwatini',
    'Gambia, The': 'Gambia', 
    'The Gambia': 'Gambia', 
    'Korea, South': 'South Korea', 
    'North Macedonia': 'Macedonia', 
    'Serbia': 'Republic of Serbia',
    'Taiwan*': 'Taiwan',
    'Tanzania': 'United Republic of Tanzania',
    'Timor-Leste': 'East Timor',
    'Bahamas, The': 'The Bahamas',
    'US': 'United States of America',
    'Holy See': 'Italy'    # church jurisdiction and not country (vatican)
}

df.replace({"country": country_map}, inplace=True)


# left join so only countries we have geometries for are in the mapping dataset
merged = gdf.merge(df, left_on = 'country', right_on = 'country', how='left')
merged = merged.drop(['country_code'], axis=1)

# re-convert day (including the NaN rows) to the correct string date format 
merged['day'] = pd.to_datetime(merged['day']).dt.strftime("%Y-%m-%d")

## Add missing date rows for countries with no cases

# create tmp table of all combinations of country X date
country_date_cols = ['country', 'day']
lists_of_uniques = [merged[col].unique() for col in country_date_cols]
tmp = pd.DataFrame(list(itertools.product(*lists_of_uniques)), columns=country_date_cols)

# add geometry from country borders
tmp = tmp.merge(gdf[['country', 'geometry']], left_on = 'country', right_on = 'country', how='left')

# outer join to add missing rows - will join on common columns
merged = merged.merge(tmp, how='outer')

# del rows with day='NaT'
merged = merged.loc[merged['day'] != 'NaT']




## Subset to 2 dates for testing
#merged_subset = merged.loc[merged['day'].isin(['2020-03-01', '2020-03-02'])]
merged_subset = merged

## PLOT

def slider_callback(attr, old, new):
    """Update numbers based on selected date"""
    day = date_slider.value
    new_data = source_by_date(data, day)
    source.geojson = new_data.to_json() # overwrite the existing source's geojson

def menu_callback(attr, old, new):
    """Update color shading by selected metric"""
    if menu.value == 'Confirmed': 
        metric = 'confirmed'  
        color_mapper.palette = brewer['Purples'][9][::-1]
        hover = HoverTool(tooltips=[('UN Country', '@country'), ('Confirmed', '@confirmed')])
        p1.add_tools(hover)
        
    
    elif menu.value == 'Recovered': 
        metric = 'recovered'
        color_mapper.palette = brewer['Greens'][9][::-1]
        hover = HoverTool(tooltips=[('UN Country', '@country'), ('Recovered', '@recovered')])
        p1.add_tools(hover)
        
    elif menu.value == 'Deaths':
        metric = 'deaths'
        color_mapper.palette = brewer['Reds'][9][::-1]
        hover = HoverTool(tooltips=[('UN Country', '@country'), ('Deaths', '@deaths')])
        p1.add_tools(hover)
        
    vals = data[metric]    
    color_mapper.low = vals.min()
    color_mapper.high = vals.max()
    color_bar.color_mapper = color_mapper

        
data = merged_subset

start_date = datetime.datetime.date(datetime.datetime.strptime(data['day'].min(), "%Y-%m-%d")) 
end_date = datetime.datetime.date(datetime.datetime.strptime(data['day'].max(), "%Y-%m-%d"))
print(start_date, end_date)

selected_day = end_date
source = source_by_date(data, selected_day)
source = GeoJSONDataSource(geojson=json.dumps(json.loads(source.to_json()))) # GeoJSONDataSource only works with string dates. Have to use geojsondatasource for mapping.

# set the defaults
metric = 'confirmed'
palette = brewer['Blues'][9][::-1]

# set the initial colour map and tooltips
vals = data[metric]
color_mapper = LinearColorMapper(palette=palette, low=vals.min(), high=vals.max(), 
                                 nan_color = '#d9d9d9') # note NaN color arg is ignored... known bug.

color_bar = ColorBar(color_mapper=color_mapper, label_standoff=8, #width=500, height=20,
                         location=(0,0), orientation='horizontal')

# TOOLTIPS = [
#     ('UN country', '@country'),
#     ('Confirmed', '@confirmed'),
#     ('Recovered', '@recovered'),
#     ('Deaths', '@deaths')
# ]

p1 = figure(title='Global Records', 
           plot_height=600 , plot_width=850, 
           toolbar_location='right', 
           tools='wheel_zoom, pan, reset',
           #tooltips=TOOLTIPS,
           x_axis_label='Longitude', y_axis_label='Latitude')

p1.xgrid.grid_line_color = None
p1.ygrid.grid_line_color = None

p1.patches('xs','ys', 
          source=source,
          fill_alpha=1, line_width=0.5, line_color='black',  
          fill_color={'field': metric, 'transform': color_mapper})

hover = HoverTool(tooltips=[('UN Country', '@country'), ('Confirmed', '@confirmed')])

date_slider = DateSlider(title='Date', value=end_date, start=start_date, end=end_date, step=1)
date_slider.on_change('value', slider_callback)

p1.add_layout(color_bar, 'below')
p1.add_tools(hover)

menu = Select(options=['Confirmed', 'Recovered', 'Deaths'], value='Confirmed', title='Metric')
menu.on_change('value', menu_callback)

### LAYOUT WITHOUT TABS
#layout = row(p1, column(menu, date_slider))
#curdoc().add_root(layout) 


### LAYOUT WITH TABS
p2 = figure(title='Individual Country Records - IN PROG', 
           plot_height=600 , plot_width=850, 
           toolbar_location='right', 
           tools='wheel_zoom, pan, reset',
           x_axis_label='Longitude', y_axis_label='Latitude')

# TAB 1: world map to show all countries, with date slider and metric selector
tab1 = Panel(child=row(p1, column(menu, date_slider)), title='Global Records') 

# TAB 2: Drop down to select country, with time series bar chart for each metric, and possibly table of data by province
tab2 = Panel(child=p2, title='Country Selector')

layout = Tabs(tabs=[tab1, tab2])
curdoc().add_root(layout) 
