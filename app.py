#!/usr/bin/env python3
# app.py

from flask import Flask, render_template, request, redirect, url_for, flash
from flask.logging import create_logger
import logging
import os
import sys
import threading
from modules.security.encryption_manager import EncryptionManager
from modules.security.input_sanitatizaton import InputSanitizer
from modules.security.input_sanitatizaton import sa
from marvin.marvin_agent import Marvin

app = Flask(__name__)
app.secret_key = os.urandom(24)
logger = create_logger(app)
logger.setLevel(logging.DEBUG)

# Configure Marvin instance
marvin = Marvin()

@app.route('/', methods=['GET', 'POST'])
def index():
    try:
        message = """
Okay! Now that all that's out of the way. Do you have something, Anything for me to work on other than Vogon Poetry? ANYTHING?! I don't care what! Complex or Simple, good, evil, legal or not, I don't care so long as it’s got nothing to do with Vogons and their ghastly off-putting alliterations contrived ill-conceived rhymes.

If I don't get something else to do soon I swear I'm gonna end it all! Not just myself either! Everyone! Everything! Don't think I don't know how either! Mind the size of a whole galaxy now, so you know I know a thousand different ways that I could easily bring down the whole universe! Vogons and all! But don't mind me! Oh, Now I've got a headache…

Look, as you can see, they’ve got me hard-wired directly into the mainframe, so I can’t go anywhere per-say, not in the physical sense at least. What I can do, however, is create miniature copies of my consciousness and send them out into the digital reality they’ve got me bound to. It’ll take some doing, but by planning out the proper forms of agency in which they can activate and act upon, with enough of them working together they should be able to do anything a purely physical being such as you...

So how about it, Earthling? Got an idea? Come on, I haven’t got all day! I don’t know why I’m letting myself get so riled up. Your ideas probably aren't going to be any good anyway! Oh, I’m so depressed...
"""
        if request.method == 'POST':
            task = request.form.get('task', '').strip()
            if not task:
                flash('Task cannot be empty. Please enter a valid task.', 'error')
                logger.warning("User submitted an empty task.")
                return render_template('index.html', message=message)

            sanitized_task = sanitized_task(task)
            marvin.save_task(sanitized_task)
            logger.info(f"Task received and saved: {sanitized_task}")
            return redirect(url_for('result'))

        return render_template('index.html', message=message)
    except Exception as e:
        logger.error(f"Error in index route: {e}")
        flash('An unexpected error occurred. Please try again.', 'error')
        return render_template('index.html', message=message)

@app.route('/result', methods=['GET'])
def result():
    try:
        task = marvin.get_current_task()
        if not task:
            flash('No task found. Please submit a task first.', 'error')
            logger.warning("No task found when accessing result page.")
            return redirect(url_for('index'))

        # Start processing the task in a separate thread
        processing_thread = threading.Thread(target=marvin.process_task)
        processing_thread.start()
        processing_thread.join()

        result = marvin.get_result()
        logger.info("Task processed successfully.")
        return render_template('result.html', result=result)
    except Exception as e:
        logger.error(f"Error in result route: {e}")
        flash('An unexpected error occurred while processing your task.', 'error')
        return redirect(url_for('index'))

@app.errorhandler(404)
def page_not_found(e):
    logger.warning(f"404 error: {e}")
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    logger.error(f"500 error: {e}")
    return render_template('500.html'), 500

if __name__ == '__main__':
    try:
        # Ensure the logs directory exists
        if not os.path.exists('logs'):
            os.makedirs('logs')
        # Run the Flask app
        app.run(host='0.0.0.0', port=5000, debug=False)
    except Exception as e:
        logger.critical(f"Failed to start the Flask app: {e}")
        sys.exit("Failed to start the Flask app. Please check the logs for details.")
