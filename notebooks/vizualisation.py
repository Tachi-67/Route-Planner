import pandas as pd
output = pd.read_csv('output.csv').drop(columns=['Unnamed: 0'])
name_mapping = {'stop_id1':'from', 'stop_id2': 'to', 'transport_type':'transport','index':'trip_id', 
                'departure_time':'departure'}
output = output.rename(columns=name_mapping)

# +
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import ipywidgets as widgets
from IPython.display import display, clear_output, HTML

# Small color widget
class ColorWidget(widgets.Widget):
    def _init_(self, color):
        super()._init_()
        self.color = color

    @property
    def color(self):
        return self._color

    @color.setter
    def color(self, value):
        self._color = value
        self._update_style()

    def _update_style(self):
        style = f"background-color: {self.color}; width: 20px; height: 20px;"
        self.layout = widgets.Layout(width="20px", height="20px", border="1px solid black")
        self.style = style

        

# Example data for demonstration
df = pd.DataFrame({
    'trip_id': [10, 200, 200],
    'departure': ['11h', '11:30h', '12h'],
    'transport': ['bus', 'walk', 'plane'],
    'confidence': [89.0, 94.0, 94.0], 
    'from': ['Zurich Airport', 'Zurich Airport', 'Zurich Old Town'],
    'lat1': [47.450199, 47.450199, 47.372127],
    'lon1': [8.563171, 8.563171, 8.542319],
    'to': ['Zurich Lake', 'Zurich Old Town', 'Zurich Lake'],
    'lat2': [47.366856, 47.372127, 47.366856],
    'lon2': [8.544755, 8.542319, 8.544755]
})

# Unique trip_ids
trip_ids = df['trip_id'].unique()

# Assign unique color to each trip_id
colors = px.colors.qualitative.Safe[:len(trip_ids)]

# Dictionary to map trip_ids to colors
color_mapping = dict(zip(trip_ids, colors))

# New 'color' column based on trip_id
df['color'] = df['trip_id'].map(color_mapping)

# Group the data by trip_id, aggregate the stations
grouped = df.groupby('trip_id').agg({'from': 'first', 'to': 'last'}).reset_index()

# Scrollable list widget
options = [f"Route {i+1} - {df[df.trip_id==trip_id].confidence.iloc[0]}%"
           for i, trip_id in enumerate(df.trip_id.unique())]
list_widget = widgets.Select(
    options=options,
    #description='Best Routes:',
    rows=len(grouped),
    layout=widgets.Layout(height='300px')
)

# Output area for the route overview
output_area = widgets.Output()

# Color Widget
color_widget = ColorWidget(color=df['color'][0])

# Function to update the route overview
def update_route_overview(change):
    selected_trip_id = change['new']
    ind = options.index(selected_trip_id)
    selected_trip_id = grouped['trip_id'].iloc[ind]
    selected_route = df[df['trip_id'] == selected_trip_id]
    selected_color = df['color'].iloc[ind]  # Color corresponding to the selected trip_id

    with output_area:
        clear_output()
        
        # Create and display the color widget
        color_widget.color = selected_color
        
        # Display more detailed route information
        dspl_routes = selected_route.reset_index()[['transport', 'departure', 'from', 'to']]
        dspl_routes.index = dspl_routes.index + 1
        display(dspl_routes)

# Register the update function to the list widget's on_change event
list_widget.observe(update_route_overview, 'value')

# Scatter mapbox trace for starting points
start_trace = go.Scattermapbox(
    lat=df['lat1'],
    lon=df['lon1'],
    mode='markers',
    marker=dict(
        size=10,
        color=df['color'],
        opacity=0.7,
        showscale=False
    ),
    text=df['from'],  # Location name for hover text
    hovertemplate='<b>Location:</b> %{text}<br><extra></extra>'  # Hover template
)

# Scatter mapbox trace for destination points
destination_trace = go.Scattermapbox(
    lat=df['lat2'],
    lon=df['lon2'],
    mode='markers',
    marker=dict(
        size=10,
        color=df['color'],
        opacity = 0.7,
        showscale=False
    ),
    text=df['to'],  # Location name for hover text
    hovertemplate='<b>Location:</b> %{text}<extra></extra>'  # Hover template
)

# Line traces for connections with the same color as trip_id
line_traces = []
for _, row in df.iterrows():
    og_color = row['color']
    opacity = 0.7
    transparent_color = f'rgba{og_color[3:-1]}, {opacity})'
    line_trace = go.Scattermapbox(
        lat=[row['lat1'], row['lat2'], None],
        lon=[row['lon1'], row['lon2'], None],
        mode='lines',
        line=dict(
            #color=row['color'],
            color=transparent_color,
            width=5
        ),
        text=df['trip_id'],  # Location name for hover text
        hovertemplate='<b>Location:</b> %{text}<extra></extra>'  # Hover template
    )
    line_traces.append(line_trace)

# Data list containing all traces
data = line_traces + [start_trace, destination_trace]

# Set up the layout for the map
layout = go.Layout(
    title='Transit Routes',
    showlegend=False,
    mapbox=dict(
        style='carto-positron',
        zoom=9,
        center=dict(lat=df['lat1'].mean(), lon=df['lon1'].mean())
    ),
    height=600,
    width=800,
    margin=dict(l=0, r=0, t=0, b=300)  # Manual margin/padding around the map
)

# Create the figure
fig = go.Figure(data=data, layout=layout)

# Create the output widget for the graph
graph_widget = widgets.Output()

# Function to render the graph inside the output widget
def render_graph():
    with graph_widget:
        clear_output()
        fig.show()

# Render the initial graph
render_graph()

# Container layout aligned to the left
container = widgets.HBox([list_widget, output_area, graph_widget])
container.layout.align_items = 'flex-start'

# Display the widgets
display(color_widget)
display(container)

# Manually trigger the change event
selected_trip_id = options[0]  # Example: change to the desired trip_id
change = {'new': selected_trip_id}
update_route_overview(change)
