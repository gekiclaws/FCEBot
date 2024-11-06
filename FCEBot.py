import discord
from discord.ext import commands
import pandas as pd
import numpy as np
import math
import configparser  # to parse the config.ini
import os

# -------------
# CONFIGURATION
# -------------

# Initialize the config parser
config = configparser.ConfigParser()
# Read the config.ini file
config.read('config.ini')
# Get the token from the config file
TOKEN = config.get('discord', 'token')

# -------------
# PREPROCESSING
# -------------

# Load the FCE data from the CSV file
table = pd.read_csv('fce.csv')

# Convert the table to a numpy array and ensure all data is cast to string for consistency
table = np.array(table).astype(str)

# -------------------------------
# THE BOT - ACADEMIC SECTION
# -------------------------------

# Define the bot's intents
intents = discord.Intents.default()
intents.message_content = True  # Enable the intent to read message content

# Create the bot instance with the intents
client = commands.Bot(command_prefix='&', intents=intents)

@client.event
async def on_ready():
    """
    Prints some stuff to the console so I know the bot's ready.
    """
    print('Logged in as')
    print(client.user.name)
    print(client.user.id)
    print('------')


def isValidCourse(msg): 
    """
    Helper function that identifies if a string is a valid course or not.
    """
    if len(msg) == 5 and msg.isdigit():
        return True
    if len(msg) == 6 and (msg[:2] + msg[3:]).isdigit() and msg[2] == '-':
        return True
    return False

def isValidArgs(ctx, args):
    """
    Helper function that classifies what type of parameters were passed in.
    """
    lastArg = 0
    for i, arg in enumerate(args):
        if i == 0 and (not isValidCourse(arg)):
            return False, None, None, 1 # not valid args, display message 1 (courseID not given)
        if isValidCourse(arg): # moves up the index of the last valid course argument
            lastArg = i
    if len(args) == lastArg + 3 and args[lastArg + 1].isdigit() and args[lastArg+2].count('.') <= 1 and args[lastArg+2].replace('.', '', 1).isdigit():
        if not args[-1].isdigit():
            if float(args[-1]) >= 0 and float(args[-1]) <= 1:
                return True, True, 2, 0 # valid args, passed a float filter arg, passed both optional parameters, no early return
            else:
                return False, None, None, 2 # not valid args, display error message 2 (optional args incorrect) 
        else:
            return True, False, 2, 0 # valid args, passed an integer filter arg, passed both optional parameters, no early return
    elif len(args) == lastArg + 2 and args[lastArg + 1].isdigit():
        return True, None, 1, 0 # valid args, passed num semesters optional parameter, no early return
    elif len(args) == lastArg + 1:
        return True, None, 0, 0 # valid args, passed no optional parameters, no early return
    return False, None, None, 2 # invalid args, display error message 2 (args incorrect)


def getString(mold, row):
    """
    Takes particular columns from an FCE data frame row and assembles them into a string.
    """
    indices = [0, 1, 6, 10, 9, 11, 12]
    rowIndices = [row[index] for index in indices]
    string = mold.format(*rowIndices)
    return string

def toDigitString(ID):
    """
    Turns a course ID argument into a compatible form for the FCE data frame.
    """
    if ID.isdigit():
        if ID[0] == '0':
            return ID[1:]
        return ID
    else:
        if ID[0] == '0':
            return ID[:1] + ID[3:]
        return ID[:2] + ID[3:]

@client.command(pass_context=True)
async def fce(ctx, *args):
    """
    Function that defines the &fce command.
    """
    indices = [0, 1, 4, 7, 6, 10, 9, 11, 12]
    valid, isFloat, condition, msg = isValidArgs(ctx, args) # sets some indicator variables that will alter the flow of the function
    if msg == 1:
        await ctx.channel.send('Invalid arguments - please specify the course ID (e.g. \"&fce 21127 2\")')
    elif msg == 2:
        await ctx.channel.send('Invalid arguments - please follow the `&fce [courseIDs...] [opt: # sem] [opt: # / prop. responses]` format.')
    if not valid:
        return

    # Set the courseID(s)
    lastCourse = 0
    for i, arg in enumerate(args):
        if isValidCourse(arg):
            lastCourse = i

    courseIDs = [toDigitString(args[i]) for i in range(lastCourse + 1)]

    # Segments the data by year, semester
    allRows = []
    for courseID in courseIDs:
        year = None
        semester = None
        courseList = []
        sameSemList = []
        for row in table:
            if row[0] != year or row[1] != semester:  # if this row is not the same course/semester as the rest of the section
                if len(sameSemList) != 0:
                    courseList.append(sameSemList)
                sameSemList = []
                year = row[0]
                semester = row[1]
            if str(row[4]) == str(courseID):  # Ensure both course ID and row[4] are strings
                sameSemList.append(row)
        allRows.append(courseList)

    # Restricts to the rows requested
    if condition == 2 and isFloat:
        newRows = [[row for i, sameSemList in enumerate(courseList) for row in sameSemList if i < int(args[-2]) and float(row[11]) >= (100 * float(args[-1]))] 
        for courseList in allRows]
    elif condition == 2 and not isFloat:
        newRows = [[row for i, sameSemList in enumerate(courseList) for row in sameSemList if i < int(args[-2]) and int(row[10]) >= int(args[-1])]
        for courseList in allRows]
    else:
        numSemesters = 2
        if condition == 1:
            numSemesters = int(args[-1])
        newRows = [[row for i, sameSemList in enumerate(courseList) for row in sameSemList if i < numSemesters]
        for courseList in allRows]

    # Adds up the FCE's
    totalFCEs = []
    totalFCE_hours = 0  # Track total FCE hours for all courses
    course_details = []  # To store each course's formatted output

    for i, rows in enumerate(newRows):
        totalFCE = 0
        count = 0
        course_name = ""
        for row in rows:
            if not math.isnan(float(row[12])):  # Ensure row[12] is cast to float for math operations
                totalFCE += float(row[12])
                course_name = row[7]  # Get the course name
                count += 1
        if count == 0:
            await ctx.channel.send('Course not found: {}'.format(courseIDs[i]))
            return
        avg_fce = np.around(totalFCE / count, 1)  # Average FCE for the course
        totalFCEs.append(avg_fce)
        totalFCE_hours += avg_fce  # Add to total FCE hours

        # Format the course output: "XX-XXX (COURSE NAME) = X.X hours/week"
        formatted_course_id = f"**{courseIDs[i][:2]}-{courseIDs[i][2:]}**"  # Format course ID as XX-XXX
        course_details.append(f"{formatted_course_id} ({course_name}) = **{avg_fce} hours/week**")

    # Add the total FCE line
    course_details.append(f"Total FCE = **{np.around(totalFCE_hours, 1)} hours/week**")
    
    # Join all course details and send the final message
    final_response = "\n".join(course_details)
    await ctx.channel.send(final_response)

@client.command(pass_context=True)
async def course(ctx, courseID):
    """
    Function that defines the &course command.
    """
    # Since we're no longer using the cmu_course_api, we'll need to find course information
    # directly from the CSV data. Let's assume we can get the details from the loaded table.
    
    if isValidCourse(courseID):  # if the courseID is valid, then do all the work
        # Remove hyphen if it exists
        if courseID[2] == "-":
            courseID = courseID[:2] + courseID[3:]

        # Find course in the CSV dataset
        course_data = table[table[:, 4] == str(courseID)]  # Ensure proper comparison as string
        
        if len(course_data) == 0:
            await ctx.channel.send('Course not found.')
            return

        # Extract information from the first matching row
        course_row = course_data[0]
        title = course_row[7]
        department = course_row[3]
        instructor = course_row[6]
        total_students = course_row[9]
        response_rate = course_row[10]
        fce_hours = course_row[11]
        overall_course_rating = course_row[12]

        # Create an embed message with the course information
        embed = discord.Embed(title="__**{}**__".format(title), colour=discord.Colour(0xA6192E), description=
            '**Department:** {}\n**Instructor:** {}\n**Total Students:** {}\n**Response Rate:** {}%\n**FCE Hours:** {}\n**Overall Course Rating:** {}'.format(
                department, instructor, total_students, response_rate, fce_hours, overall_course_rating))
        
        await ctx.channel.send(embed=embed)
    else:
        await ctx.channel.send('Invalid arguments - please specify the course ID (e.g. \".course 21127)\"')

client.run(TOKEN)