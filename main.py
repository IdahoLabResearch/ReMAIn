import streamlit as st

import pandas as pd
import numpy as np

import plotly.graph_objects as go


# Set the page title and layout
st.set_page_config(page_title='INLs Flex Power', layout="wide")


def get_asset_flexibility(asset, time):
	'''The flexibility of an asset in terms of real power ramping up and down'''

	# If there is no asset set the ramping up and down to 0
	if asset == None:
		return {'Up': 0, 'Down': 0, 'Output': 0}
	
	# Get the ramping up capability of the asset
	up = time * asset['Ramp Up'] - asset['Latency'] * asset['Ramp Up']
	up = np.where(up < 0, 0, up)
	up = np.where(up > asset['Max Output'] - asset['Output'], asset['Max Output'] - asset['Output'], up)

	# Get the ramping down capability of the asset
	down = time * -asset['Ramp Down'] - asset['Latency'] * -asset['Ramp Down']
	down = np.where(down > 0, 0, down)
	down = np.where(down < asset['Min Output'] - asset['Output'], asset['Min Output'] - asset['Output'], down)

	# If there is and energy limit, i.e. battery storage
	if 'Charge' in asset:
		energy_to_empty = asset['Charge'] * asset['Energy'] / 100
		energy_to_full = asset['Energy'] - energy_to_empty

		dt = time[1] - time[0]
		up   = np.where(up.cumsum() * dt > energy_to_empty, 0, up)
		down = np.where(-down.cumsum() * dt > energy_to_full, 0, down)

	return {'Up': up, 'Down': down, 'Output': asset['Output']}



def get_power_disturbance_curve(time, system):
	'''The power disturbance curve gives the time a power system will go from its current frequency 
	to a frequency limit based on the size of disturbance. The larger the inertia, the longer the time.
	The larger the disturbance, the shorter time. The closer to a frequency limit, the shorter time.'''
	
	# The inertia in the system
	K = system['inertia']

	# The real-time kinetic energy
	J = (2 * K)  / ((4 * np.pi * system['freq'] / 2 ) ** 2)
	
	# The kinetic energy at the frequency max/min
	K_m  = (1/2 * J)  * (4 * np.pi * system['freq min'] / 2)  ** 2
	K_M  = (1/2 * J)  * (4 * np.pi * system['freq max'] / 2)  ** 2

	# The available kinetic energy in either direction
	K_a_m = K - K_m
	K_a_M = K_M - K

	# The power disturbance curve. i.e. time the system has after a disturbance based on size and kinetic energy.
	P_d_m = K_a_m / time
	P_d_M = -K_a_M / time

	return {'lower': P_d_M, 'upper': P_d_m}


def flexibility_aggreagation(gas_fired_flex, hydro_flex, solar_flex, wind_flex, battery_flex):
	'''The aggregation of all the assets, i.e. the systems ability to ramp up and down in real power.'''

	flex_up   = gas_fired_flex['Up']   + hydro_flex['Up']   + solar_flex['Up']   + wind_flex['Up']   + battery_flex['Up']
	flex_down = gas_fired_flex['Down'] + hydro_flex['Down'] + solar_flex['Down'] + wind_flex['Down'] + battery_flex['Down']
	return {'Up': flex_up, 'Down': flex_down}


def get_max_min_disturbance(system_flex, disturbance_curve, time):
	'''The maximum disturbance size is where the ramping of real power corosses the power disturbance curve.
	Here, the ramping has rebalanced the disturbance size at the frequency limit.'''

	idx_down = np.argwhere(disturbance_curve['lower']  > system_flex['Down'])[0]
	idx_up   = np.argwhere(disturbance_curve['upper'] < system_flex['Up'])[0]

	return {'max dist': disturbance_curve['upper'][idx_up], 
	        'min dist': disturbance_curve['lower'][idx_down], 
	        'max dist @time': time[idx_up], 
	        'min dist @time': time[idx_down]}

######################
# Figure Functions
######################

def figure_asset_flexibility(time, flex):
	'''Plot an assets flexibility in real power from its current operating point'''

	fig = go.Figure(go.Scatter(x=np.concatenate([time, time[::-1]]),
							   y=np.concatenate([flex['Up'] + flex['Output'], flex['Down'][::-1] + flex['Output']]),
							   fill='toself', hoveron='points'))

	fig.update_layout(margin=dict(l=10, r=10, b=0, t=0), 
					  xaxis_title="time (s)",
    				  yaxis_title="Power (MW)", 
    				  height=200,
    				  showlegend=False,
    				  font=dict(size=15))
	return fig



def figure_power_disturbance_curve(disturbance_curve):
	'''Plot the power disturbance curve'''

	fig = go.Figure()
	fig.add_trace(go.Scatter(x=time, y=disturbance_curve['upper'], mode="lines", line=go.scatter.Line(color='black'), showlegend=False))
	fig.add_trace(go.Scatter(x=time, y=disturbance_curve['lower'], mode="lines", line=go.scatter.Line(color='black'), showlegend=False))
	fig.update_layout(margin=dict(l=10, r=10, b=0, t=0), xaxis_title='time (s)', yaxis_title='Disturbance (MW)', yaxis_range=[-100, 100], height=200, font=dict(size=15))
	return fig



def figure_system_flex_power_disturbance(system_flex, disturbance_curve):
	'''Plot the systems flexibility or ramping up and down in real power'''

	fig = go.Figure()
	fig.add_trace(go.Scatter(x=np.concatenate([time, time[::-1]]), 
		                     y=np.concatenate([system_flex['Up'], system_flex['Down'][::-1]]),
		                     fill='toself'))
	fig.add_trace(go.Scatter(x=time, y=disturbance_curve['upper'], mode="lines", line=go.scatter.Line(color="black"), showlegend=False))
	fig.add_trace(go.Scatter(x=time, y=disturbance_curve['lower'], mode="lines", line=go.scatter.Line(color="black"), showlegend=False))
	
	fig.update_layout(margin=dict(l=10, r=10, b=0, t=0), 
    				  xaxis_title="time (s)",
    				  yaxis_title="Flex/Disturbance (MW)", 
    				  yaxis_range=[min(system_flex['Down'])*1.4, max(system_flex['Up'])*1.4],
    				  height=400,
    				  showlegend=False,
    				  font=dict(size=15))
	return fig


###########################
# Frontend and user input
###########################

st.sidebar.markdown('## System Generation Assets')

# Get the assets to be used in the system
sys_assets = st.sidebar.expander('Asset Types')
has_gas_fired = sys_assets.checkbox('Gas-fired', True)
has_hydro = sys_assets.checkbox('Hydro', True)
has_solar = sys_assets.checkbox('Solar', True)
has_wind = sys_assets.checkbox('Wind', True)
has_battery = sys_assets.checkbox('Battery Storage', True)


st.sidebar.markdown('## System Inertia & Frequency')
sys = st.sidebar.expander('Inertia & Frequency Settings')

# Get the inertia and frequency limts
inertia = sys.number_input('Total Inertia (MWs)', min_value=0.0, value=50.0, step=25.0)
f_min   = sys.number_input('Minimum Frequency (Hz)', min_value=57.0, max_value=59.9, value=59.0, step=0.1)
f_max   = sys.number_input('Maximum Frequency (Hz)', min_value=60.1, max_value=63.0, value=61.0, step=0.1)
f       = sys.number_input('System Frequency (Hz)', min_value=f_min, max_value=f_max, value=60.0) 
system  = {'inertia': inertia, 'freq': f, 'freq min': f_min, 'freq max': f_max}

# The maximum time to be displayed in the plots
time_max = sys.number_input('Max plot time (s)', min_value=2, value=5, step=3)
time = np.linspace(0.1, time_max, 1000)


############################
# Frontend plots
############################

figure_list = []
heading_list = []

st.sidebar.markdown('## Asset Characteristics')

if has_gas_fired is True:
	gas_fire = st.sidebar.expander('Gas-fired Generation')
	gas_fire_P_max     = gas_fire.number_input('Maximum Output (MW)', min_value=0.0, value=10.0)
	gas_fire_P_0       = gas_fire.number_input("Power Output (MW)", min_value=0.0, max_value=gas_fire_P_max, value=7.0)
	gas_fire_latency   = gas_fire.number_input('Latency (s)', min_value=0.1, value=1.0, step=0.1)
	gas_fire_ramp_up   = gas_fire.number_input('Ramp up (MW/s)', min_value=0.1, value=1.0, step=0.25)
	gas_fire_ramp_down = gas_fire.number_input('Ramp down (MW/s)', min_value=0.1, value=1.5, step=0.25)
	gas_fire_asset     = {'Output': gas_fire_P_0, 'Max Output': gas_fire_P_max, 'Min Output': 0, 'Latency': gas_fire_latency, 'Ramp Up': gas_fire_ramp_up, 'Ramp Down': gas_fire_ramp_down}
	gas_fired_flex  = get_asset_flexibility(gas_fire_asset, time) 

	figure_list.append(figure_asset_flexibility(time, gas_fired_flex))
	heading_list.append('##### Gas-fired Generation')

else:
	gas_fired_flex  = get_asset_flexibility(None, time)


if has_hydro is True:
	hydro = st.sidebar.expander('Hydro Generation')
	hydro_P_max     = hydro.number_input('Maximum Output (MW)', min_value=0.0, value=10.0, step=0.25)
	hydro_P_0       = hydro.number_input("Power Output (MW)", min_value=0.0, max_value=hydro_P_max, value=5.0, step=0.25)
	hydro_latency   = hydro.number_input('Latency (s)', min_value=0.1, value=1.0, step=0.05)
	hydro_ramp_up   = hydro.number_input('Ramp up (MW/s)', min_value=0.1, value=1.0, step=0.1)
	hydro_ramp_down = hydro.number_input('Ramp down (MW/s)', min_value=0.1, value=2.5, step=0.1)
	hydro_asset       = {'Output': hydro_P_0, 'Max Output': hydro_P_max, 'Min Output': 0, 'Latency': hydro_latency, 'Ramp Up': hydro_ramp_up, 'Ramp Down': hydro_ramp_down}
	hydro_flex  = get_asset_flexibility(hydro_asset, time) 
	
	figure_list.append(figure_asset_flexibility(time, hydro_flex))
	heading_list.append('##### Hydro Generation')

else:
	hydro_flex  = get_asset_flexibility(None, time)

if has_solar is True:
	solar = st.sidebar.expander('Solar Generation')
	solar_max       = solar.number_input('Maximum Output (MW)', min_value=0.0, value=1.0, step=0.05)
	solar_P_0       = solar.number_input("Power Output (MW)", min_value=0.0, max_value=solar_max, value=1.0, step=0.05)
	solar_latency   = solar.number_input('Latency (s)', min_value=0.01, value=0.05, step=0.01)
	solar_ramp_up   = solar.number_input('Ramp up (MW/s)', min_value=0.5, value=25.0, step=2.0)
	solar_ramp_down = solar.number_input('Ramp down (MW/s', min_value=0.5, value=25.0, step=2.0)
	solar_asset     = {'Output': solar_P_0, 'Max Output': solar_max, 'Min Output': 0, 'Latency': solar_latency, 'Ramp Up': solar_ramp_up, 'Ramp Down': solar_ramp_down}
	solar_flex      = get_asset_flexibility(solar_asset, time)

	figure_list.append(figure_asset_flexibility(time, solar_flex))
	heading_list.append('##### Solar Generation')

else:
	solar_flex  = get_asset_flexibility(None, time)


if has_wind is True:
	wind = st.sidebar.expander('Wind Generation')
	wind_max       = wind.number_input('Maximum Output (MW)', min_value=0.0, value=2.0, step=0.1)
	wind_P_0       = wind.number_input("Power Output (MW)", min_value=0.0, max_value=wind_max, value=1.0, step=0.2)
	wind_latency   = wind.number_input('Latency (s)', min_value=0.1, value=0.1, step=0.1)
	wind_ramp_up   = wind.number_input('Ramp up (MW/s)', min_value=0.5, value=10.0, step=1.0)
	wind_ramp_down = wind.number_input('Ramp down (MW/s', min_value=0.5, value=10.0, step=1.0)
	wind_asset     = {'Output': wind_P_0, 'Max Output': wind_max, 'Min Output': 0, 'Latency': wind_latency, 'Ramp Up': wind_ramp_up, 'Ramp Down': wind_ramp_down}
	wind_flex      = get_asset_flexibility(wind_asset, time)
	
	figure_list.append(figure_asset_flexibility(time, wind_flex))
	heading_list.append('##### Wind Generation')

else:
	wind_flex  = get_asset_flexibility(None, time)



if has_battery is True:
	battery = st.sidebar.expander('Battery Storage')
	battery_max       = battery.number_input('Maximum Output (MW)', min_value=0.0, value=0.5, step=0.05)
	battery_min       = battery.number_input('Minimum Output (MW)', max_value=0.0, value=-0.5, step=0.05)
	battery_P_0       = battery.number_input("Power Output (MW)", min_value=battery_min, max_value=battery_max, value=-0.5, step=0.1)
	battery_latency   = battery.number_input('Latency (s)', min_value=0.005, value=0.1, step=0.01)
	battery_ramp_up   = battery.number_input('Ramp up (MW/s)', min_value=0.5, value=50.0, step=5.0)
	battery_ramp_down = battery.number_input('Ramp down (MW/s', min_value=0.5, value=50.0, step=5.0)
	battery_charge    = battery.number_input('Charge (%)', min_value=0.0, value=75.0, max_value=100.0, step=2.0)
	battery_energy    = battery.number_input('Energy Capacity (MWs)', min_value=0.0, value=1000.0, step=10.0)	
	battery_asset     = {'Energy': battery_energy, 'Charge': battery_charge, 'Output': battery_P_0, 'Max Output': battery_max, 'Min Output': battery_min, 'Latency': battery_latency, 'Ramp Up': battery_ramp_up, 'Ramp Down': battery_ramp_down}
	battery_flex      = get_asset_flexibility(battery_asset, time)
	
	figure_list.append(figure_asset_flexibility(time, battery_flex))
	heading_list.append('##### Battery Storage')

else:
	battery_flex  = get_asset_flexibility(None, time)


disturbance_curve = get_power_disturbance_curve(time, system)
dist_fig = figure_power_disturbance_curve(disturbance_curve)


if len(figure_list) == 1:
	pass
	# System is plotted below
elif len(figure_list) == 2:
	col_1, col_2, col_3 = st.columns(3)
	col_1.markdown(heading_list[0])
	col_2.markdown(heading_list[1])
	col_3.markdown('##### Power Disturbance Curve')

	col_1.plotly_chart(figure_list[0], use_container_width=True)
	col_2.plotly_chart(figure_list[1], use_container_width=True)
	col_3.plotly_chart(dist_fig, use_container_width=True)

elif len(figure_list) == 3:
	col_1, col_2, col_3, col_4 = st.columns(4)
	col_1.markdown(heading_list[0])
	col_2.markdown(heading_list[1])
	col_3.markdown(heading_list[2])
	col_4.markdown('##### Power Disturbance Curve')

	col_1.plotly_chart(figure_list[0], use_container_width=True)
	col_2.plotly_chart(figure_list[1], use_container_width=True)
	col_3.plotly_chart(figure_list[2], use_container_width=True)
	col_4.plotly_chart(dist_fig, use_container_width=True)

elif len(figure_list) == 4:
	col_1, col_2, col_3, col_4 = st.columns(4)
	col_1.markdown(heading_list[0])
	col_2.markdown(heading_list[1])
	col_3.markdown(heading_list[2])
	col_4.markdown(heading_list[3])

	col_1.plotly_chart(figure_list[0], use_container_width=True)
	col_2.plotly_chart(figure_list[1], use_container_width=True)
	col_3.plotly_chart(figure_list[2], use_container_width=True)
	col_4.plotly_chart(figure_list[3], use_container_width=True)

elif len(figure_list) == 5:
	col_1, col_2, col_3, col_4, col_5 = st.columns(5)
	col_1.markdown(heading_list[0])
	col_2.markdown(heading_list[1])
	col_3.markdown(heading_list[2])
	col_4.markdown(heading_list[3])
	col_5.markdown(heading_list[4])

	col_1.plotly_chart(figure_list[0], use_container_width=True)
	col_2.plotly_chart(figure_list[1], use_container_width=True)
	col_3.plotly_chart(figure_list[2], use_container_width=True)
	col_4.plotly_chart(figure_list[3], use_container_width=True)
	col_5.plotly_chart(figure_list[4], use_container_width=True)



system_flex = flexibility_aggreagation(gas_fired_flex, hydro_flex, solar_flex, wind_flex, battery_flex)

col_5, col_6 = st.columns([2,1])
fig_5 = figure_system_flex_power_disturbance(system_flex, disturbance_curve)
col_5.markdown('##### System Flexibility and Power Disturbance Curve')
col_5.plotly_chart(fig_5, use_container_width=True)

col_6.markdown('##### System Information & Results')
disturbance_info = get_max_min_disturbance(system_flex, disturbance_curve, time)


col_6.markdown(f'System Inertia: {inertia:.1f} MWs')
col_6.markdown(f'System Frequency: {f:.1f} Hz')
col_6.markdown(f'Frequency Limits: {f_min:.2f} and {f_max:.1f} Hz')

if has_gas_fired:
	col_6.markdown(f'Gas-fired Generation: {gas_fire_P_0:.1f} MW')
if has_hydro:
	col_6.markdown(f'Hydro Generation: {hydro_P_0:.1f} MW')
if has_solar:
	col_6.markdown(f'Solar Generation: {solar_P_0:.2f} MW')
if has_wind:
	col_6.markdown(f'Wind Generation: {wind_P_0:.2f} MW')
if has_battery:
	col_6.markdown(f'Battery Generation: {battery_P_0:.2f} MW')
#col_6.markdown(f'Battery Capacity {battery_energy} MWs @ {battery_charge}% charge')

col_6.markdown(f'Maximum disturbance: {float(disturbance_info["max dist"]):.2f} MW')# at {float(disturbance_info["max dist @time"]):.2f}s')
col_6.markdown(f'Minimum disturbance: {float(disturbance_info["min dist"]):.2f} MW')# at {float(disturbance_info["min dist @time"]):.2f}s')

