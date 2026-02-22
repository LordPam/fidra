"""Search service for boolean query filtering of transactions.

Supports boolean operators: AND, OR, NOT
Supports grouping with parentheses: (term1 OR term2) AND term3
Case-insensitive matching across all searchable fields.
"""

from typing import Callable
from enum import Enum
import re

from fidra.domain.models import Transaction


class TokenType(Enum):
    """Token types for query parsing."""
    TERM = "TERM"
    AND = "AND"
    OR = "OR"
    NOT = "NOT"
    LPAREN = "LPAREN"
    RPAREN = "RPAREN"


class Token:
    """A token in the search query."""

    def __init__(self, type: TokenType, value: str):
        """Initialize token.

        Args:
            type: Token type
            value: Token value
        """
        self.type = type
        self.value = value

    def __repr__(self):
        return f"Token({self.type}, {self.value!r})"


class SearchService:
    """Service for searching transactions with boolean queries.

    Features:
    - Boolean operators: AND, OR, NOT
    - Grouping with parentheses
    - Case-insensitive search
    - Searches across description, category, party, notes

    Example queries:
        "coffee"                    - Simple term search
        "coffee AND fuel"           - Both terms must match
        "coffee OR fuel"            - Either term must match
        "NOT pending"               - Exclude pending
        "(coffee OR fuel) AND car"  - Grouped conditions
        '"Social Event"'            - Exact phrase search
    """

    def search(self, transactions: list[Transaction], query: str) -> list[Transaction]:
        """Filter transactions by boolean search query.

        Args:
            transactions: List of transactions to search
            query: Boolean search query string

        Returns:
            Filtered list of matching transactions

        Example:
            >>> service = SearchService()
            >>> results = service.search(transactions, "coffee AND NOT pending")
        """
        if not query or not query.strip():
            return transactions

        try:
            # Parse query into tokens
            tokens = self._tokenize(query)

            # Convert to Reverse Polish Notation
            rpn = self._to_rpn(tokens)

            # Compile RPN to matcher function
            matcher = self._compile_rpn(rpn)

            # Filter transactions
            return [t for t in transactions if matcher(t)]

        except Exception:
            # On parse error, return all transactions
            # Could also return empty list or raise - UX decision
            return transactions

    def _tokenize(self, query: str) -> list[Token]:
        """Parse query string into tokens.

        Args:
            query: Raw query string

        Returns:
            List of tokens

        Example:
            >>> tokens = self._tokenize("coffee AND (fuel OR car)")
            >>> # [Token(TERM, 'coffee'), Token(AND, 'AND'), ...]
        """
        tokens = []
        i = 0
        query = query.strip()

        while i < len(query):
            # Skip whitespace
            if query[i].isspace():
                i += 1
                continue

            # Left parenthesis
            if query[i] == '(':
                tokens.append(Token(TokenType.LPAREN, '('))
                i += 1
                continue

            # Right parenthesis
            if query[i] == ')':
                tokens.append(Token(TokenType.RPAREN, ')'))
                i += 1
                continue

            # Quoted phrase - treat entire contents as a single term
            if query[i] == '"':
                i += 1  # skip opening quote
                start = i
                while i < len(query) and query[i] != '"':
                    i += 1
                phrase = query[start:i]
                if i < len(query):
                    i += 1  # skip closing quote
                if phrase:
                    tokens.append(Token(TokenType.TERM, phrase))
                continue

            # Read word
            start = i
            while i < len(query) and not query[i].isspace() and query[i] not in '()"':
                i += 1

            word = query[start:i]
            word_upper = word.upper()

            # Check if operator
            if word_upper == 'AND':
                tokens.append(Token(TokenType.AND, 'AND'))
            elif word_upper == 'OR':
                tokens.append(Token(TokenType.OR, 'OR'))
            elif word_upper == 'NOT':
                tokens.append(Token(TokenType.NOT, 'NOT'))
            else:
                # Term (search keyword)
                tokens.append(Token(TokenType.TERM, word))

        return tokens

    def _to_rpn(self, tokens: list[Token]) -> list[Token]:
        """Convert tokens to Reverse Polish Notation using Shunting-yard algorithm.

        Args:
            tokens: Infix token list

        Returns:
            RPN token list

        Example:
            >>> rpn = self._to_rpn([Term('a'), AND, Term('b')])
            >>> # [Term('a'), Term('b'), AND]
        """
        # Operator precedence (higher = binds tighter)
        precedence = {
            TokenType.NOT: 3,
            TokenType.AND: 2,
            TokenType.OR: 1,
        }

        output = []
        operator_stack = []

        for token in tokens:
            if token.type == TokenType.TERM:
                output.append(token)

            elif token.type in (TokenType.AND, TokenType.OR, TokenType.NOT):
                # Pop operators with higher or equal precedence
                while (operator_stack
                       and operator_stack[-1].type != TokenType.LPAREN
                       and precedence.get(operator_stack[-1].type, 0) >= precedence[token.type]):
                    output.append(operator_stack.pop())

                operator_stack.append(token)

            elif token.type == TokenType.LPAREN:
                operator_stack.append(token)

            elif token.type == TokenType.RPAREN:
                # Pop until matching left paren
                while operator_stack and operator_stack[-1].type != TokenType.LPAREN:
                    output.append(operator_stack.pop())

                # Pop the left paren
                if operator_stack:
                    operator_stack.pop()

        # Pop remaining operators
        while operator_stack:
            output.append(operator_stack.pop())

        return output

    def _compile_rpn(self, rpn: list[Token]) -> Callable[[Transaction], bool]:
        """Compile RPN token list into a matcher function.

        Args:
            rpn: RPN token list

        Returns:
            Matcher function that takes a transaction and returns True if it matches

        Example:
            >>> matcher = self._compile_rpn(rpn_tokens)
            >>> matcher(transaction)  # True or False
        """
        def matcher(transaction: Transaction) -> bool:
            """Match transaction against compiled query."""
            stack = []

            for token in rpn:
                if token.type == TokenType.TERM:
                    # Term: check if it matches transaction
                    text = self._get_searchable_text(transaction)
                    matches = token.value.lower() in text.lower()
                    stack.append(matches)

                elif token.type == TokenType.AND:
                    # AND: both operands must be True
                    if len(stack) < 2:
                        return False
                    right = stack.pop()
                    left = stack.pop()
                    stack.append(left and right)

                elif token.type == TokenType.OR:
                    # OR: either operand can be True
                    if len(stack) < 2:
                        return False
                    right = stack.pop()
                    left = stack.pop()
                    stack.append(left or right)

                elif token.type == TokenType.NOT:
                    # NOT: negate operand
                    if len(stack) < 1:
                        return False
                    operand = stack.pop()
                    stack.append(not operand)

            # Final result
            return stack[0] if stack else False

        return matcher

    def _get_searchable_text(self, transaction: Transaction) -> str:
        """Extract all searchable text from transaction.

        Args:
            transaction: Transaction to extract text from

        Returns:
            Combined searchable text (space-separated)

        Example:
            >>> text = self._get_searchable_text(transaction)
            >>> # "Coffee Shop Coffee expense pending Jane's Coffee"
        """
        parts = [
            transaction.description,
            str(transaction.amount),
            transaction.type.value,
            transaction.status.value,
        ]

        if transaction.category:
            parts.append(transaction.category)

        if transaction.party:
            parts.append(transaction.party)

        if transaction.reference:
            parts.append(transaction.reference)

        if transaction.activity:
            parts.append(transaction.activity)

        if transaction.notes:
            parts.append(transaction.notes)

        return ' '.join(parts)
