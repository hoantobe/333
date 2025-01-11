import psycopg2
import os
try:
  
    conn = psycopg2.connect(
        dbname="tobesite",
        user="tobesite",
        password="SuJqiCkeWckpWXYuvseGWe1lbB11iau5",
        host= "dpg-ctppp623esus73dk4bkg-a.oregon-postgres.render.com",
        port="5432"
    )
    print("Connection successful")
except Exception as e:
    print(f"Error: {e}")

