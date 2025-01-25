import random
import uuid
import nltk
from nltk.corpus import wordnet as wn
import re

# Ensure WordNet is downloaded
try:
  wn.synsets('example')
except LookupError:
  nltk.download('wordnet')

# Define a regex pattern to include only alphabetic words
word_pattern = re.compile(r'^[a-zA-Z]+$')

# Pre-fetch and clean adjective list from WordNet
adjectives = list(set(
  lemma.name().lower()
  for synset in wn.all_synsets(pos=wn.ADJ)
  for lemma in synset.lemmas()
  if word_pattern.match(lemma.name())
))

# Pre-fetch and clean noun list from WordNet
nouns = list(set(
  lemma.name().lower()
  for synset in wn.all_synsets(pos=wn.NOUN)
  for lemma in synset.lemmas()
  if word_pattern.match(lemma.name())
))

def generate_random_name():
  """
  Generates a random name in the format:
  'adjective-noun-xx'
  
  Where:
  - 'adjective' is a randomly selected adjective from WordNet.
  - 'noun' is a randomly selected noun from WordNet.
  - 'xx' is a two-character hexadecimal suffix.
  
  Returns:
      str: The generated name.
  """
  # Select a random adjective and noun
  adj = random.choice(adjectives)
  noun = random.choice(nouns)
  
  # Generate a two-character hexadecimal suffix
  suffix = uuid.uuid4().hex[:2]
  
  # Combine into the final name
  return f"{adj}-{noun}-{suffix}"

# Example usage
if __name__ == "__main__":
  for _ in range(5):
    print(generate_random_name())
