# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: light
#       format_version: '1.5'
#       jupytext_version: 1.14.5
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---


# +
from datetime import datetime
import math
import networkx as nx
import pyarrow.parquet as pq
import pandas as pd
from hdfs3 import HDFileSystem

from heapq import heappush, heappop


# -

def create_multigraph(edges):
    g = nx.MultiDiGraph()

    for edge in edges:
        trip_id = edge[2]["trip_id"]
        route_id = edge[2]["route_id"]
        stop_id1 = edge[0]
        stop_id2 = edge[1]
        used_time = edge[2]["time"]
        if g.has_edge(stop_id1, stop_id2):
            edgesNow = g[stop_id1][stop_id2]
            same_route_id_exists = any(route_id == edgeNow["route_id"] for edgeNow in edgesNow.values())
            if not same_route_id_exists: # no edge of same route_id exists
                g.add_edge(stop_id1, stop_id2, key=route_id, used_time=used_time, route_id = route_id)
        else: #not edge exists at all
            g.add_edge(stop_id1, stop_id2, key=route_id ,used_time=used_time, route_id = route_id)
    
    return g

def multi_path_weight(G, total_path):
    total_cost = 0
    route_ids = []
    
    #Iterate over the stops
    for i in range(len(total_path)-1):
        edge_data = G.get_edge_data(total_path[i],total_path[i+1])
        
        #Temporary workaround, but this should NEVER be true
        #if edge_data is None:
        #    continue
        
        #If there is a single edge between stops
        if 'used_time' in edge_data:
            total_cost += edge_data['used_time']
            route_ids.append(edge_data['route_id'])
        #If there are multiple paths between stops
        else:
            times = []
            edge_route_ids = []
            #Store the time taken for each path
            for edge_id in edge_data:
                times.append(edge_data[edge_id]['used_time'])
                edge_route_ids.append(edge_data[edge_id]['route_id'])
            #Find the fastest one
            total_cost += min(times)
            route_ids.append(edge_route_ids[times.index(min(times))])
    return total_cost, route_ids

def k_shortest_paths(G, source, target, k, weight):
    # Compute the shortest path using Dijkstra's algorithm
    shortest_path = nx.shortest_path(G, source, target, weight=weight)

    route_id_lists = [] # records of route_id of each path
    
    # Initialize the list of k-shortest paths
    paths = [shortest_path]
    
    total_cost, route_id_list = multi_path_weight(G, shortest_path)
    route_id_lists.append(route_id_list)
    

    # Initialize the heap to store potential candidates
    candidates = []

    for i in range(1, k):
        #print('number of paths: ', i)
        # Iterate over the nodes in the current path
        for j in range(len(paths[i - 1]) - 1):
            #print('nunber of edges:', G.number_of_edges())
            spur_node = paths[i - 1][j]
            root_path = paths[i - 1][:j + 1]

            # Remove edges that are part of previous paths
            removed_info = [] # records of removed info
            removed_dict = {} # set of removed edges info
            
            for p, path in enumerate(paths):
                if len(path) > j and path[:j + 1] == root_path:
                    u, v = path[j], path[j + 1]
                    route_id = route_id_lists[p][j]
                    dict_key = u+v+route_id
                    
                    # store edge info
                    if dict_key not in removed_dict:
                        # this edge is not a part of other paths
                        removed_dict[dict_key] = {'used_time':G[u][v][route_id]['used_time'], 'route_id': G[u][v][route_id]['route_id'] }
                        removed_info.append([ G[u][v][route_id]['used_time'], G[u][v][route_id]['route_id'] ])
                    else:
                        # this edge has been used and removed by other paths
                        removed_info.append([ removed_dict[dict_key]['used_time'], removed_dict[dict_key]['route_id'] ])
                        
                    # remove edge
                    if G.has_edge(u, v):
                        try:
                            G.remove_edge(u, v, key=route_id)
                        except:
                            pass#print('This edge has been removed by previous paths')
                    
            # Calculate the spur path from the spur node to the target
            spur_path = nx.shortest_path(G, spur_node, target, weight=weight)

            # Calculate the total path by combining the root path and spur path
            total_path = root_path + spur_path[1:]

            # Calculate the total cost of the new path
            total_cost, route_id_list = multi_path_weight(G, total_path)#nx.path_weight(G, total_path, 'used_time')

            # Add the potential candidate to the heap
            heappush(candidates, (total_cost, total_path, route_id_list))

            # Restore removed edges
            info_idx = 0
            for p, path in enumerate(paths):
                if len(path) > j and path[:j + 1] == root_path:
                    u, v = path[j], path[j + 1]
                    route_id = route_id_lists[p][j] # the recoreded route_id for this sec this path
                    removed_time = removed_info[info_idx][0]
                    removed_id = removed_info[info_idx][1]
                    G.add_edge(u,v, key=route_id, used_time=removed_time, route_id=removed_id)
                    info_idx += 1

        # Check if a new path is found
        if len(candidates) == 0:
            break

        # Select the lowest cost candidate as the new path
        lowest_cost, lowest_cost_path, lowest_route_id_list = heappop(candidates)
        paths.append(lowest_cost_path)
        route_id_lists.append(lowest_route_id_list)

    return paths, route_id_lists


# +

def calculate_connections(trans, route_ids, nodes, arrival_time):
    latest_arrivals = []

    #Keep track of the arrival time and when different routes are taken
    prev_arrival = arrival_time
    prev_route_id = route_ids[-1]
    departure_time = None

    #Generate the paths
    node_paths = [(nodes[j], nodes[j+1]) for j in range(len(nodes)-1)]
    node_paths = [(None, node_paths[0][0])] + node_paths
    route_ids = [None] + route_ids
    
    #Iterate backwards, starting from the destination
    for i, (r, edge) in enumerate(zip(route_ids[::-1],node_paths[::-1])):
        if r is None:
            break
    
        #Get the arrival stop of the corresponding route
        stop_id1 = edge[0]
        stop_id2 = edge[1]
        temp = trans[(trans.stop_id1==stop_id1)&(trans.stop_id2==stop_id2)&(trans.route_id==r)]

        #If we change routes we need to consider the 2 minute transition time
        if prev_route_id != r:
            prev_arrival = str(prev_arrival - pd.Timedelta('2 min')).split(' ')[2]
            
            #Make sure the previous stop arrives in time  
        temp = temp[temp.stop_id2_arr<=prev_arrival].sort_values('stop_id2_arr',ascending=False)
        
        if temp.empty:
            return None
        
        #Update arrival times and current route
        latest_arrivals.append(temp.iloc[0])
        trip_id = temp.trip_id.iloc[0]
        prev_arrival = temp.stop_id1_dep.iloc[0]
        prev_route_id = r
    return latest_arrivals



# +

def get_connection_info(trans, latest_arrivals, nodes, date, arr_time):
    list_input = []
    # ensemble journey info
    for i, node in enumerate(nodes[:-1]):
        # the current trip
        trip_info_this = latest_arrivals[::-1][i]
        stop_id1 = nodes[i]
        stop_id2 = nodes[i+1]
        trip_id_this = trip_info_this.trip_id
        #print(stop_id1,stop_id2,trip_id_this)
        # filter out this trip
        this_trip = trans[
            (trans.stop_id1==stop_id1) &
            (trans.stop_id2==stop_id2) &
            (trans.trip_id==trip_id_this)
        ].iloc[0]
        #print(this_trip)
        departure_time = this_trip.stop_id1_dep
        arrival_time = this_trip.stop_id2_arr
        transport_type = this_trip.route_desc
        route_id = this_trip.route_id
        # the start next trip
        if i < (len(nodes)-2) : # before destination
            trip_info_next = latest_arrivals[::-1][i+1]
            stop_id3 = nodes[i+2] # starting node of the next trip
            trip_id_next = trip_info_next.trip_id
            # filter out the next trip
            next_trip = trans[
                (trans["stop_id1"]==stop_id2) &
                (trans["stop_id2"]==stop_id3) &
                (trans["trip_id"]==trip_id_next)
                ].iloc[0]
            next_departure_time = next_trip.stop_id1_dep#.iloc[0]
            #print(next_departure_time)
            stopover_time_in_minutes = math.floor((datetime.strptime(next_departure_time, '%H:%M:%S') - datetime.strptime(arrival_time, '%H:%M:%S') ) .total_seconds() / 60)
        else: # the final journey
            next_departure_time = arr_time
            stopover_time_in_minutes = math.floor((datetime.strptime(next_departure_time, '%H:%M:%S') - datetime.strptime(arrival_time, '%H:%M:%S') ) .total_seconds() / 60)
        list_input.append([stop_id1, stop_id2,departure_time,arrival_time,transport_type,date,stopover_time_in_minutes, route_id])
    return list_input


# -

def calculate_total_time(df):
    t1 = pd.Timedelta(df.departure_time.iloc[0])
    t2 = pd.Timedelta(df.arrival_time.iloc[-1])
    return (t2-t1).total_seconds()
