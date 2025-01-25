import nltk
from nltk.corpus import brown
from nltk import pos_tag
from collections import Counter
import string

nltk.download('brown')       # Brown Corpus
nltk.download('universal_tagset')  # Universal POS Tagset
nltk.download('punkt')       # Tokenizer models
nltk.download('averaged_perceptron_tagger_eng')


# Load sentences from the Brown Corpus
sentences = brown.sents()


# Initialize a list to hold all nouns
nouns = []

# Iterate through each sentence in the corpus
for sentence in sentences:
    # Tokenize and tag each sentence
    tagged_sentence = pos_tag(sentence, tagset='universal')
    
    # Extract words tagged as 'NOUN'
    for word, tag in tagged_sentence:
        if tag == 'NOUN':
            # Clean the word: remove punctuation and make lowercase
            word = word.lower().strip(string.punctuation)
            # Ensure the word is alphabetic and has exactly 4 letters
            if word.isalpha() and len(word) == 4:
                nouns.append(word)


# Count the frequency of each noun
noun_freq = Counter(nouns)

# Filter nouns to ensure they have exactly 4 letters (redundant if already filtered)
four_letter_nouns = {word: freq for word, freq in noun_freq.items() if len(word) == 4}

lst_nouns = [(word, freq) for word, freq in four_letter_nouns.items()]
lst_sorted = sorted(lst_nouns, key=lambda x: x[1], reverse=True)
nouns = [word for word, freq in lst_sorted[:250]]


