from flask import Flask, request, render_template, jsonify, redirect, url_for
from flask_api import status
from flask_cors import CORS, cross_origin
import uuid
import json
import xlrd
import numpy as np
import csv
from BeautifulSoup import BeautifulSoup
import requests
import logging
import sqlite3 as sqllite
import sys


SENTIMENT_WS_URL = "http://peerlogic.csc.ncsu.edu/sentiment"

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

def initialize_metadata():
    metadata = {
        'v_labels': [],
        'h_labels': [],
        'font-size': 12,
        'font-face': 'Arial',
        'showTextInsideBoxes': True,
        'showCustomColorScheme': False,
        'tooltipColorScheme': 'black',
        "color_scheme": {
            "ranges": [{
                "minimum": -1.5,
                "maximum": -0.5,
                "color": "#E74C3C"
            }, {
                "minimum": -0.5,
                "maximum": 0,
                "color": "#F1948A"
            }, {
                "minimum": 0,
                "maximum": 0.5,
                "color": "#82E0AA"
            }, {
                "minimum": 0.5,
                "maximum": 1.5,
                "color": "#229954"
            }]
        },
        "content":[]
    }

    return metadata


def get_sentiment(text):
    url = SENTIMENT_WS_URL + '/analyze_review'
    if len(text) > 0:
        return requests.post(url, json={"review":text}).json()["overall_compound"]
    else:
        return 0

def get_sentiment_bulk(reviews):
    url = SENTIMENT_WS_URL + '/analyze_reviews_bulk'
    if len(reviews) > 0:
        return requests.post(url, json={"reviews":reviews}).json()["sentiments"]
    else:
        return []

def parse_csv(file):
    #log the headers
    header1 = file.readline()
    header2 = file.readline()
    instructor_logger.info(header1)
    instructor_logger.info(header2)

    #check if this is CPR data file
    if "Assignment =" in header1 and "Time =" in header2:
        metadata = initialize_metadata()

        #read the file
        reader = csv.reader(file, dialect="excel")
        cpr_data = list(reader)

        #find the last row in this file. CPR data file is inconsistent it may contain empty fields.
        last_row = len(cpr_data[0])
        for i in range(len(cpr_data[0])-1,0, -1):
            if cpr_data[0][i] == '':
                last_row-=1;
            else:
                break

        comment_cols = []
        h_labels = []
        #find the comment cols in this file.
        for i in range(6, last_row):
            if 'Explanation' in cpr_data[0][i]:
                comment_cols.append(i)
                h_labels.append(cpr_data[0][i])

        metadata["h_labels"] = h_labels

        v_labels = []
        content = []


        sentiment_request = []

        j = 0
        for row in range(1, len(cpr_data)):
            author_id = cpr_data[row][0]
            author_name = cpr_data[row][2]
            reviewer = cpr_data[row][4]
            cpi = cpr_data[row][5]

            #this is a self review row, we should skip this for now
            if reviewer == "":
                continue

            v_labels.append(author_name)

            row_content = []
            for i in range(0, len(comment_cols)):
                #insert cell in a row
                c={}
                c['text'] = BeautifulSoup(cpr_data[row][comment_cols[i]]).text
                c['value'] = 0

                req ={}
                req['text'] = c['text']
                req['id'] = "" + str(j) + "_" + str(i) + ""
                sentiment_request.append(req)
                #logging.debug("comment: " + c['comment']+ " SA:" + str(c['value']))
                row_content.append(c)
            #insert each row
            content.append(row_content)
            j += 1

        sentiments = get_sentiment_bulk(sentiment_request)

        for s in sentiments:
            row_col = s['id'].split("_")
            row = int(row_col[0])
            col = int(row_col[1])
            #debug_logger.debug("row:" + row_col[0] + " col:" + row_col[1])
            #debug_logger.debug("len_row:" + str(len(content)) + " len_col:" + str(len(content[row])))
            content[row][col]['value'] = s['sentiment']

        metadata["v_labels"] = v_labels
        metadata["content"] = content

        return metadata

def parse_xls(file):

    return None

def parse_xlsx(file):
    return None


@app.route('/')
def index():
    return redirect('developer')

@app.route('/file-upload', methods=['POST'])
@cross_origin()
def file_upload():
    file = request.files['file']

    #check type of the files, find a way to check the header
    if file.filename.endswith(".csv"):
        config = parse_csv(file)
    elif file.filename.endswith(".xls"):
        config = parse_xls(file)
    elif file.filename.endswith(".xlsx"):
        config = parse_xlsx(file)
    else:
        debug_logger.error("someone uploaded unknown file (" + file.filename + ")" )
        return jsonify(error="Uploaded file is currently not supported"), status.HTTP_415_UNSUPPORTED_MEDIA_TYPE

    return jsonify(config), status.HTTP_200_OK

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

    query = "INSERT INTO Config (id, json ) VALUES(?, ?)"
    cur.execute(query, (str(id), json.dumps(request.json)))

    con.commit()

    return jsonify(url="http://peerlogic.csc.ncsu.edu/reviewsentiment/viz/" + id.urn[9:])
    #return jsonify(url="http://127.0.0.1:3009/viz/" + id.urn[9:])

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
    #app.run(host='127.0.0.1', port=3009, threaded=True)
    app.run(host='0.0.0.0', port=3009, threaded=True)
