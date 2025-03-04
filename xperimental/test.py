import pandas as pd

class ColorDataFrame(pd.DataFrame):
  """
  A DataFrame subclass that colors specific rows red when printed in a console.

  Parameters
  ----------
  *args : tuple
    Positional arguments passed to the pd.DataFrame constructor.
  color_condition : callable, optional
    A function that takes a row (pd.Series) and returns True if the row should be
    highlighted in red, or False otherwise.
  **kwargs : dict
    Keyword arguments passed to the pd.DataFrame constructor.

  Returns
  -------
  ColorDataFrame
    A subclass of DataFrame that overrides the to_string method for coloring.

  Examples
  --------
  
  >>> df = ColorDataFrame(
        df,
  ...   color_condition=lambda row: row['value'] > 9
      )  
  >>> print(df)
  """

  _metadata = ['_color_condition']

  def __init__(self, *args, color_condition=lambda row: False, **kwargs):
    super().__init__(*args, **kwargs)
    # Store the condition function as an attribute
    self._color_condition = color_condition
    return

  def to_string(self, *args, **kwargs):
    """
    Overridden version of to_string that applies ANSI colors to rows
    matching the condition.
    """
    original_string = super().to_string(*args, **kwargs)
    # Split the original string into lines
    lines = original_string.split('\n')

    header_lines = lines[:1]
    data_lines = lines[1:]

    colored_data_lines = []
    for row_index, row_line in enumerate(data_lines):
      # Attempt to parse the index from the leftmost part of each row line
      try:
        # The row's index in the actual DataFrame
        df_index = self.index[row_index]
      except IndexError:
        colored_data_lines.append(row_line)
        continue

      # Check if row meets the color condition
      if self._color_condition(self.loc[df_index]):
        # Red color ANSI: \033[91m ... \033[0m
        row_line = f"\033[91m{row_line}\033[0m"

      colored_data_lines.append(row_line)

    return "\n".join(header_lines + colored_data_lines)


if __name__ == "__main__":
  df = ColorDataFrame({'value': [10, -5, 3]}, color_condition=lambda row: row['value'] > 9)
  print(df)
