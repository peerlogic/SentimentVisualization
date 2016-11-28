from flask import Flask, request, render_template, jsonify, redirect, url_for
from flask_api import status
from flask_cors import CORS, cross_origin
import uuid
import json
import xlrd
import numpy as np
import csv
import logging

import sqlite3 as sqllite
import sys


formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')

# first file logger
instructor_logger = logging.getLogger('instructor_logger')
hdlr_1 = logging.FileHandler('instructor.log')
hdlr_1.setFormatter(formatter)
instructor_logger.addHandler(hdlr_1)
instructor_logger.setLevel(logging.INFO)

# second file logger
debug_logger = logging.getLogger('debug_logger')
hdlr_2 = logging.FileHandler('debug.log')
hdlr_2.setFormatter(formatter)
debug_logger.addHandler(hdlr_2)
debug_logger.setLevel(logging.ERROR)

app = Flask(__name__)
CORS(app)

configTable = {}
cur = None
con = None

def setup_sql_lite_db():
    try:

        global con
        con = sqllite.connect('config_json.db', check_same_thread=False)
        global cur
        cur = con.cursor()
        #cur.execute('DROP TABLE IF EXISTS Comment')
        sql = "CREATE TABLE IF NOT EXISTS Config (" \
              "    id VARCHAR, " \
              "    json TEXT)"
        cur.execute(sql)
        con.commit()

    except sqllite.Error, e:
        print "Error %s:" % e.args[0]
        sys.exit(1)

@app.route('/')
def index():
    return redirect('developer')

#TODO refactor exctract each file processing to a method
@app.route('/file-upload', methods=['POST'])
@cross_origin()
def file_upload():
    file = request.files['file']

    #check type of the files, find a way to check the header
    if file.filename.endswith(".csv"):

    elif file.filename.endswith(".xls"):

    elif file.filename.endswith(".xlsx"):

    else:
        debug_logger.error("someone uploaded unknown file (" + file.filename + ")" )
        return jsonify(error="Uploaded file is currently not supported"), status.HTTP_415_UNSUPPORTED_MEDIA_TYPE


    return jsonify([config]), status.HTTP_200_OK

@app.route('/instructor', methods=['GET'])
@cross_origin()
def instructor():
    return render_template('instructor.html')


@app.route('/developer', methods=['GET'])
@cross_origin()
def developer():
    return render_template('developer.html')

@app.route('/configure', methods=['POST'])
@cross_origin()
def configure():
    global cur, con

    # generate id
    id = uuid.uuid4();

    cur.execute("INSERT INTO Config (id, json ) VALUES('" + str(id) + "', '" + json.dumps(request.json) + "')")
    con.commit()

    #return jsonify(url="http://peerlogic.csc.ncsu.edu/rainbowgraph/viz/" + id.urn[9:])
    return jsonify(url="http://127.0.0.1:3008/viz/" + id.urn[9:])

@app.route('/viz/<id>', methods=['GET', 'DELETE'])
@cross_origin()
def visualize(id):
 global cur, conn

 if request.method == 'DELETE':
    cur.execute("DELETE FROM Config WHERE id='" + id + "'")
    con.commit()

    return "", status.HTTP_200_OK
 else:
     cur.execute("SELECT json FROM Config WHERE id='" + id + "'")
     rows = cur.fetchall()

     if len(rows) == 0:
         return jsonify(error="Shoot.. I couldn't find the config data")
     else:
         return render_template('visualization.html', json_data = rows[0])

if __name__ == '__main__':
    setup_sql_lite_db()
    app.run(host='127.0.0.1', port=3005, threaded=True)
    #app.run(host='0.0.0.0', port=3008, threaded=True)
