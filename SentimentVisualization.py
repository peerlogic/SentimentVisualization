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
import yaml
import json

# load config file
global cfg
with open("config_file.yml", 'r') as ymlfile:
    cfg = yaml.load(ymlfile)


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
    url = cfg['SENTIMENT_WS_URL'] + '/analyze_review'
    if len(text) > 0:
        return requests.post(url, json={"review":text}).json()["overall_compound"]
    else:
        return 0

def get_sentiment_bulk(reviews):
    url = cfg['SENTIMENT_WS_URL'] + '/analyze_reviews_bulk'
    if len(reviews) > 0:
        return requests.post(url, json={"reviews":reviews}).json()["sentiments"]
    else:
        return []

#only CPR format is supported
def parse_csv(file):
    #log the headers
    header1 = file.readline()
    header2 = file.readline()


    #check if this is CPR data file
    if "Assignment =" in header1 and "Time =" in header2:
        #log this upload
        instructor_logger.info(header1)
        instructor_logger.info(header2)

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
                c['text'] = json.dumps(BeautifulSoup(cpr_data[row][comment_cols[i]]).text.rstrip())
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

#only SWORD/Perceptive format is supported
def parse_xls(file):

    book = xlrd.open_workbook(file_contents=file.read())
    data_sheet = book.sheet_by_index(0)
    reviewer_col = 1
    dimension_name_col = 2
    comment_id_col = 3
    comment_col = 5
    backeval_col = 6

    #log the headers
    i = 0
    while True:
        first_cell = data_sheet.cell(i,0).value
        if first_cell != "":
            instructor_logger.info(first_cell)

        # assume the first column of SWORD data is started with Author
        if "Paper Author" == first_cell:
            j = 0
            for row in range(i, data_sheet.ncols):
                if data_sheet.cell(i,j).value == "Reviewer":
                    reviewer_col = j
                elif data_sheet.cell(i,j).value == "Dimension name":
                    dimension_name_col = j
                elif data_sheet.cell(i,j).value == "Comment ID":
                    comment_id_col = j
                elif data_sheet.cell(i,j).value == "Comment Content":
                    comment_col = j
                elif data_sheet.cell(i,j).value == "BackEval Comment":
                    backeval_col = j
                j+=1
            i+=1
            break;
        elif i >= data_sheet.nrows:
            debug_logger.info("unsupported data is uploaded, can't find \"Paper Author\" title in the 1st column and all rows")
            return None
        i+=1

    metadata = initialize_metadata()
    prev_dimension_name = ""
    prev_reviewer = ""
    prev_author = ""
    prev_comment_id = ""
    aggregated_comment = ""
    dimensions = {}
    sa_request = []
    v_labels = []
    content = []
    sentiments = {}

    # i now is the index of the first data, iterate to the end of the data sheet
    new_row_index = 0
    comment_no = 1
    for row in range(i, data_sheet.nrows):
        author = data_sheet.cell(row, 0).value
        reviewer = data_sheet.cell(row, reviewer_col).value
        dimension_name = data_sheet.cell(row, dimension_name_col).value
        comment_id = data_sheet.cell(row, comment_id_col).value
        comment = data_sheet.cell(row, comment_col).value
        backeval = data_sheet.cell(row, backeval_col).value

        if author == "" and reviewer == "":
            continue

        # aggregate comments addressed for a dimenstion
        if prev_comment_id == comment_id:
            comment_no += 1
            aggregated_comment += " [" + str(comment_no) + "] " + BeautifulSoup(comment, convertEntities=BeautifulSoup.HTML_ENTITIES).text.rstrip()
        # this must be the first row with a comment, store the first comment
        elif prev_comment_id == "":
            aggregated_comment = " [" + str(comment_no) + "] " + BeautifulSoup(comment, convertEntities=BeautifulSoup.HTML_ENTITIES).text.rstrip()
        # we find a different dimension, add the previous one to sa_request
        else:
            comment_no = 1
            if aggregated_comment != "":
                dict = {'id': prev_comment_id, 'text':json.dumps(aggregated_comment.replace("\r\n",""))[1:-1]}
                sa_request.append(dict)
            dimensions[prev_comment_id] = prev_dimension_name
            aggregated_comment = "[" + str(comment_no) + "] " + BeautifulSoup(comment, convertEntities=BeautifulSoup.HTML_ENTITIES).text.rstrip()


        # we find another reviewer-reviewee pair, get the sentiment value for the previous ones.
        if (prev_reviewer != reviewer or prev_author != author) and (prev_reviewer != "" and prev_author != ""):
            # analyze sentiment
            if len(sa_request) > 0:
                sentiments = get_sentiment_bulk(sa_request)
            # reset the request variable
            sa_request = []
            # add this review to v_label
            v_labels.append(prev_reviewer + " -reviews-> " + prev_author)
            # map the tone to json
            new_row = [None] * len(sentiments)
            for s in sentiments:
                #debug_logger.debug("row:" + row_col[0] + " col:" + row_col[1])
                #debug_logger.debug("len_row:" + str(len(content)) + " len_col:" + str(len(content[row])))
                col = dimensions.keys().index(s['id'])
                new_row[col] = {'value':s['sentiment'], 'text':s['text']}
            content.append(new_row)

        prev_comment_id = comment_id
        prev_reviewer = reviewer
        prev_dimension_name = dimension_name
        prev_author = author
        new_row_index += 1

    metadata["v_labels"] = v_labels
    metadata["h_labels"] = dimensions.values()
    metadata["content"] = content

    return metadata

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

    return jsonify(url=cfg['SERVER_URL']+ "/viz/" + id.urn[9:])

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
     try:
        w = int(request.args.get('width'))
     except:
        w = None

     try:
        h = int(request.args.get('height'))
     except:
        h = None

     if len(rows) == 0:
         return jsonify(error="Shoot.. I couldn't find the config data")
     else:
         data = json.loads(rows[0][0])
         w = len(data['h_labels']) * 200 if w == None else w
         h = len(data['v_labels']) * 80 if h == None else h
         return render_template('visualization.html', json_data = rows[0], width=w, height=h)

if __name__ == '__main__':
    setup_sql_lite_db()
    #app.run(host='127.0.0.1', port=3009, threaded=True)
    app.run(host='0.0.0.0', port=3009, threaded=True)
