'''
Beginner notes for anki_voice_field

This file is not part of the running app.
It is a guided explanation of how the project works.

Triple quotes like this create a multi-line Python string.
Python allows these strings in a file even if we do not assign them to a
variable. That makes them useful as big visible teaching notes.

The running project files should stay cleaner and more compact.
This file is where we can explain slowly.
'''


'''
1. What problem are we solving?

While reviewing Anki cards, you want to press a hotkey, speak, and append
that speech to the current card's note field called "Lecture Notes".

The important word is append.

Append means "add to the end".

We do not replace the old field.
We do not edit lots of cards.
We only touch the one note connected to the current reviewed card.
'''


'''
2. The full program flow

The whole app is basically this:

1. Wait for F8.
2. Start recording the microphone.
3. Wait for F8 again.
4. Stop recording.
5. Save the audio as a .wav file.
6. Transcribe that audio into text.
7. Ask AnkiConnect which card is currently being reviewed.
8. Get that card's note.
9. Read the note's fields.
10. Choose the safest field to append into.
11. Add a timestamped voice-note block to the bottom.
12. Save only that one field on only that one note.
13. Read it back to verify it really saved.

Important speed detail:

The app locks the card ID and note ID when recording starts.
That means you can move to the next card after you stop recording.
The app will still append to the original note you were talking about.
'''


'''
3. Why AnkiConnect?

AnkiConnect is an Anki add-on that opens a tiny local web API.

Local means it runs on your own computer.
API means another program can ask it to do things.

Our Python code sends messages to:

    http://localhost:8765

"localhost" means "this same computer".

We are not sending your Anki cards to some random website.
We are talking to Anki Desktop through a local port.
'''


'''
4. What is a card vs a note?

In Anki, a note stores the actual fields.

Example fields:

    Text
    Extra
    Lecture Notes
    First Aid

A card is what you review.
A note can create one or more cards.

This project starts from the current card, then asks:

    "Which note owns this card?"

Then it edits one field on that note.

Usually that field is "Lecture Notes".

If the note does not have "Lecture Notes", the program chooses a fallback field.
'''


'''
5. What config.py does

config.py stores settings.

Example:

    TARGET_FIELD_NAME = "Lecture Notes"
    HOTKEY = "<f8>"
    ANKI_CONNECT_URL = "http://localhost:8765"

Putting settings in one file makes the rest of the code easier to read.
If you want to change F8 to another key later, config.py is where you look.
'''


'''
6. What anki_client.py does

anki_client.py is responsible for talking to AnkiConnect.

It has functions like:

    check_connection()
    get_current_card_note()
    update_note_field()

A function is a reusable named action.

Example idea:

    def say_hello():
        print("hello")

After defining it, you can call:

    say_hello()

In our project, instead of "say hello", the functions do useful Anki jobs.
'''


'''
6.1. How the target field fallback works

The original version only knew one destination:

    Lecture Notes

That is very safe, but it has a problem:

    Some notes do not have a Lecture Notes field.

So now the project has a small decision function:

    choose_target_field(fields, model_name)

Think of this function like a careful checklist.

It asks:

1. Does this note have "Lecture Notes"?

    If yes, use it.

2. Does the note type look like Image Occlusion, and does it have "Remarks"?

    If yes, use Remarks.

3. Does it have a common back-side field?

    Try Back.
    Then try Extra.
    Then try Back Extra.
    Then try Remarks.

4. If none of those fields exist, stop and show an error.

This is an important programming concept:

    Make your program's choices explicit.

Explicit means the rules are written down in code instead of hidden in your head.

The fallback list lives in config.py so you can change it later without hunting
through the whole project.
'''


'''
7. What recorder.py does

recorder.py handles the microphone.

Microphones do not give us one big audio file immediately.
They give us many small chunks of sound.

The Recorder class collects those chunks while you are speaking.

A class is like a blueprint for an object.
Our Recorder object remembers:

    Am I recording right now?
    What audio chunks have I collected?
    What microphone stream is open?

When you stop recording, it combines the chunks and writes a .wav file.
'''


'''
8. What transcriber.py does

transcriber.py turns audio into text.

It uses faster-whisper, which is a local speech-to-text package.

Local speech-to-text means:

    no OpenAI API key
    no paid cloud transcription
    model runs on your computer

The first time it runs, it may download a model.
After that, it can reuse the downloaded model.
'''


'''
9. What main.py does

main.py is the command-line version of the app.

It handles commands like:

    python main.py --test-anki
    python main.py --dry-run
    python main.py

--test-anki checks the connection only.
--dry-run records and transcribes but does not write to Anki.
No flag means real mode.
'''


'''
10. What launcher.pyw does

launcher.pyw is the no-PowerShell version.

The .pyw ending means Python can run it without opening a console window.

It creates a small Tkinter window.
Tkinter is Python's built-in GUI library.

The launcher still uses the same real project logic:

    Recorder
    transcribe_audio
    get_current_card_note
    append_transcript_to_field
    update_note_field

This is good design:
the GUI is only a wrapper.
The core logic still lives in small files.
'''


'''
11. Why read-back verification matters

After writing to Anki, the app reads the same note again.

It checks:

    Does the Lecture Notes field equal what we expected?

If yes, it prints a verified success message.
If no, it raises an error.

This protects you from false confidence.
A program should not say "success" unless it knows the important thing worked.
'''


'''
11.5. Why the transcript popup exists

When the app finishes transcribing, it shows a review popup with the transcript.

This helps you quickly answer:

    "Did it hear me correctly?"

You can edit the text before saving it.
You can also cancel the write or re-record the note.

The popup appearing does not write anything yet.
The write happens when you click:

    Save To Anki

If saving fails, the app keeps the transcript and opens the review popup again.
That way you do not lose what you said.

The app also retries the Anki save internally before bothering you again.

This matters because AnkiConnect can be slow to show the saved field when the
card template or note type is large.

The retry idea is:

    write to Anki
    read the field back
    if the transcript is not there yet, wait and try again
    only fail after several attempts

One AnkiConnect limitation:

If the same note is open or selected in Anki Browser/editor, AnkiConnect may
accept the update request but not actually change the field.

That is why the app reads the field back after saving.
If the field did not change, the app tells you to close the Browser/editor and
try Save To Anki again.

The popup does not decide which note to edit.
The note was already locked at the start of recording.

This is important:

    Start recording on card A.
    Stop recording.
    Move to card B.
    Edit or re-record from the popup.

The app still targets card A's note, because card A was locked at recording
start.
'''


'''
11.5a. Why the app waits before saving sometimes

This is the section that explains the confusing part:

    Why do I have to move to the next card before saving sometimes?

Short answer:

    Because Anki may still be holding the current card's note in memory.

Longer answer:

When you are reviewing a card, Anki is not just showing static text on the
screen. It is running reviewer logic.

Reviewer logic includes things like:

    showing the question
    showing the answer
    tracking whether you pressed Again, Hard, Good, or Easy
    updating scheduling information
    keeping a copy of the card/note data while the card is active

Our voice helper is a separate Python program.

That means there are two programs involved:

    Program 1: Anki
    Program 2: our Python voice helper

Both programs can talk about the same note.

That is powerful, but it also creates a timing problem.
'''


'''
11.5a.1. The simple story

Imagine Anki has a note open in its hands.

Our helper says:

    Please add this voice note to Remarks.

AnkiConnect says:

    Okay, I wrote it.

Then our helper reads the note back and sees the transcript.

So at that exact moment, it looks like everything worked.

But Anki may still be finishing the current review card.

When you finally answer the card or move away, Anki may save its older copy of
the note.

That older copy does not include our new voice note.

So the bad sequence looks like this:

1. Anki loads card A.
2. Anki keeps an older copy of card A's note in memory.
3. Our helper writes the transcript into card A's note.
4. Our helper reads it back and sees the transcript.
5. Anki finishes the card A review action.
6. Anki saves its older copy.
7. Our transcript disappears.

This is why the helper can say "verified" and still lose the text later.

The verification was true for a moment.
It was not stable after Anki finished its own save.
'''


'''
11.5a.2. The computer science idea: state

State means the current stored information of a program.

Examples of state:

    Which Anki card is currently open?
    What text is inside the Remarks field?
    Is the microphone recording?
    What transcript did Whisper return?
    Is the review popup open?

When people say a program "has state", they mean the program remembers things.

Anki has state.
Our helper has state.

Anki's state includes the current review card.
Our helper's state includes the locked card ID, locked note ID, and transcript.

The tricky part is this:

    Two programs can have different state about the same note.

Anki might have an older in-memory copy.
AnkiConnect might briefly show our newer saved copy.

That difference is called stale state.

Stale means old or out of date.
'''


'''
11.5a.3. The computer science idea: race condition

A race condition happens when the final result depends on timing.

Here, the race is:

    Who saves last?

If our helper saves after Anki is done with the card:

    Voice note stays.

If Anki saves its older copy after our helper saves:

    Voice note disappears.

That is why the order matters.

Good order:

    Anki finishes card A.
    Helper writes the transcript.
    Transcript stays.

Bad order:

    Helper writes the transcript.
    Anki finishes card A.
    Anki overwrites the transcript with old data.

This kind of bug is annoying because every single function can look correct by
itself.

The bug comes from timing between functions.
'''


'''
11.5a.4. How our code protects against this

The helper locks onto the card at the start of recording.

It remembers:

    card_id
    note_id
    field_name
    transcript

Then, before writing, it asks Anki:

    What card is currently active in the reviewer right now?

That is what this helper function is for:

    get_current_review_card_id()

If Anki is still showing the same card we recorded on, the helper waits briefly.

The logic is:

    If current_card_id is different from target_card_id:
        safe to write

    If current_card_id is still the same as target_card_id:
        wait

    If it is still the same after waiting:
        do not write yet

The important decision is:

    It is better to pause than to pretend the save worked.

So now, if Anki is still on that same card, the helper keeps your transcript and
reopens the review popup.

Then you can:

    answer the card
    move to the next card
    click Save To Anki again

Now Anki has finished its own review work, so our helper can write afterward.
'''


'''
11.5a.5. Why the popup matters

The review popup is not just for editing the transcript.

It also protects your work.

If saving is unsafe, the popup can come back with the same transcript.

That means:

    The transcript is not thrown away.
    You do not need to re-speak the note.
    You can move off the card and retry the save.

This is a useful beginner software design principle:

    When an action fails, preserve the user's input.

In our case, the user's input is the transcript.

Losing a transcript would feel terrible because speech is hard to recreate
exactly.

So the code tries to keep the transcript alive until it is safely saved.
'''


'''
11.5a.6. The rule for using the app

The safest workflow is:

1. Look at the Anki card.
2. Press F8.
3. Speak.
4. Press F8 again to stop.
5. Move to the next card.
6. Save from the review popup.

For normal cards with Lecture Notes, saving while still on the card may work.

For Image Occlusion cards, moving off the card first is more important because
that note type seems more likely to overwrite external edits while the reviewer
is still active.

So the practical rule is:

    Stop recording first.
    Then move on.
    Then save.
'''


'''
11.5a.7. What this teaches you as a programmer

This one bug teaches several real programming lessons.

Lesson 1:

    Reading data back once does not always prove it will stay saved.

Lesson 2:

    Programs can have stale copies of data.

Lesson 3:

    Timing matters when two systems modify the same thing.

Lesson 4:

    A safe program should pause when it is unsure.

Lesson 5:

    Preserve user input when something goes wrong.

This is why programming is not only about writing syntax.

Programming is also about thinking carefully:

    Who owns this data right now?
    Could someone else overwrite it?
    What happens if this action fails?
    How do we avoid losing the user's work?
'''


'''
Old short explanation:

Anki's reviewer can still be holding the current card in memory.

That matters because this can happen:

1. The voice helper writes to the note.
2. Anki finishes answering or leaving the card.
3. Anki saves its older copy of the note afterward.

That can make our new field text disappear.

So before writing, the helper checks:

    Is Anki still showing the exact card we recorded on?

If yes, the helper waits briefly.

The goal is:

    Let Anki finish the review action first.
    Then write the voice note.

This is a common programming idea called avoiding a race condition.

A race condition means two things are trying to update related data around the
same time, and the final result depends on which one finishes last.
'''


'''
11.5b. Review mode vs fast mode

The helper now has two modes.

Review mode:

    You see an editable popup.
    You can fix the transcript.
    You click Save To Anki when ready.

Fast mode:

    The app automatically saves after transcription.
    You still get a read-only popup showing what was saved.

The checkbox is called:

    Review before saving

Checked means review mode.
Unchecked means fast mode.

This is a common app design idea:

    Give the user a safe mode and a fast mode.
'''


'''
11.6. Why the queue exists

Without a queue, the app would have to finish transcribing before you could
record another note.

That is slow for flashcards.

The queue changes the flow:

    Record card A.
    Stop recording.
    Card A audio goes into the queue.
    Move to card B.
    Record card B.
    Card B audio goes into the queue.

The worker processes the queue in the background.

Important detail:

Each queued item stores its own:

    audio file path
    card ID
    note ID
    dry-run setting

So even if you move ahead in Anki, each transcript still knows which original
note it belongs to.

The queue worker processes one audio file at a time.
That is slower than many workers, but safer because the speech model is reused
in one predictable path.
'''


'''
11.7. Why recording now starts faster

Originally, the app waited for AnkiConnect before starting the microphone.

That felt slow because AnkiConnect calls can take a couple seconds with large
AnKing card templates.

The faster version starts the microphone first, then asks AnkiConnect for the
current card in the background.

This improves the feeling of the hotkey:

    Press F8.
    Recording starts immediately.
    The app locks the visible Anki card while you are speaking.

The safety tradeoff is:

    Press F8 while the correct card is visible.
    Do not advance the card before stopping that recording.

After you stop recording, you can move on while the queue processes the audio.
'''


'''
11.8. Why the text backup log exists

The app now writes every successfully saved voice note to:

    voice_notes_log.txt

This is a simple backup outside of Anki.

Each entry stores:

    saved time
    card ID
    note ID
    transcript

The app writes to this file only after Anki has been updated and verified.

That means:

    Dry runs do not go into the backup log.
    Canceled transcripts do not go into the backup log.
    Failed saves do not go into the backup log.

This is a useful software design idea:

    First verify the important action worked.
    Then write the backup record.
'''


'''
12. What tests are for

tests/test_append_format.py checks the append formatting.

Tests are small programs that check other programs.

The most important tested behavior is:

    old notes stay
    new transcript goes at the bottom
    timestamp format is correct
    HTML characters are escaped safely

Tests let us change code later without accidentally breaking the basics.
'''


'''
13. What to learn first

Best beginner study order:

1. Read append_transcript_to_field() in anki_client.py.
2. Read tests/test_append_format.py.
3. Read get_current_card_note() in anki_client.py.
4. Read Recorder.start() and Recorder.stop() in recorder.py.
5. Read transcribe_audio() in transcriber.py.
6. Read launcher.pyw last.

Do not start with launcher.pyw.
GUI code has more moving parts and can feel confusing too early.
'''


'''
14. Important note about triple-quoted teaching notes

Triple-quoted strings are valid Python, but they are not the same as normal
# comments.

A # comment is completely ignored by Python.

A triple-quoted block creates a string object. If it appears at the top of a
file or function, Python treats it as a docstring. If it appears elsewhere like
these notes, Python still parses it as a string expression.

That is fine for a teaching file like this.

In production code, we usually use triple quotes for docstrings and # comments
for short notes. For learning visibility, this file intentionally uses triple
quotes.
'''
