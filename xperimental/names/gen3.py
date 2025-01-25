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


# Initialize a list to hold all adjs
adjs = []

# Iterate through each sentence in the corpus
for sentence in sentences:
    # Tokenize and tag each sentence
    tagged_sentence = pos_tag(sentence, tagset='universal')
    
    # Extract words tagged as 'adj'
    for word, tag in tagged_sentence:
        if tag == 'ADJ':
            # Clean the word: remove punctuation and make lowercase
            word = word.lower().strip(string.punctuation)
            # Ensure the word is alphabetic and has exactly 4 letters
            if word.isalpha() and len(word) == 4:
                adjs.append(word)


# Count the frequency of each adj
adj_freq = Counter(adjs)

# Filter adjs to ensure they have exactly 4 letters (redundant if already filtered)
four_letter_adjs = {word: freq for word, freq in adj_freq.items() if len(word) == 4}

lst_adjs = [(word, freq) for word, freq in four_letter_adjs.items()]
lst_sorted = sorted(lst_adjs, key=lambda x: x[1], reverse=True)
adjs = [word for word, freq in lst_sorted[:250]]


