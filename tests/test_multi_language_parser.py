import unittest
from pathlib import Path
import tempfile
from knowledge_graph.tree_sitter_parser import TreeSitterParser


class TestMultiLanguageParser(unittest.TestCase):
    """Test TreeSitterParser with all supported languages."""
    
    def setUp(self):
        self.parser = TreeSitterParser()
        self.temp_dir = Path(tempfile.mkdtemp())

    def test_supported_languages_count(self):
        """Test that 14 languages are supported."""
        languages = self.parser.get_supported_languages()
        self.assertEqual(len(languages), 14)
        self.assertIn("python", languages)
        self.assertIn("java", languages)
        self.assertIn("go", languages)
        self.assertIn("rust", languages)

    def test_python_parsing(self):
        """Test Python file parsing."""
        code = """
class MyClass:
    def my_method(self):
        pass

def my_function():
    return 42
"""
        test_file = self.temp_dir / "test.py"
        test_file.write_text(code)
        
        defs = self.parser.extract_definitions(test_file)
        self.assertEqual(len(defs), 3)  # class, method, function
        names = {d["name"] for d in defs}
        self.assertIn("MyClass", names)
        self.assertIn("my_method", names)
        self.assertIn("my_function", names)

    def test_java_parsing(self):
        """Test Java file parsing."""
        code = """
public class HelloWorld {
    public static void main(String[] args) {
        System.out.println("Hello");
    }
    
    private int calculateSum(int a, int b) {
        return a + b;
    }
}
"""
        test_file = self.temp_dir / "HelloWorld.java"
        test_file.write_text(code)
        
        defs = self.parser.extract_definitions(test_file)
        self.assertGreater(len(defs), 0)
        names = {d["name"] for d in defs}
        self.assertIn("HelloWorld", names)

    def test_go_parsing(self):
        """Test Go file parsing."""
        code = """
package main

func main() {
    println("Hello")
}

func add(a int, b int) int {
    return a + b
}
"""
        test_file = self.temp_dir / "main.go"
        test_file.write_text(code)
        
        defs = self.parser.extract_definitions(test_file)
        self.assertGreater(len(defs), 0)
        names = {d["name"] for d in defs}
        self.assertIn("main", names)
        self.assertIn("add", names)

    def test_rust_parsing(self):
        """Test Rust file parsing."""
        code = """
fn main() {
    println!("Hello");
}

struct Point {
    x: i32,
    y: i32,
}

impl Point {
    fn new(x: i32, y: i32) -> Point {
        Point { x, y }
    }
}
"""
        test_file = self.temp_dir / "main.rs"
        test_file.write_text(code)
        
        defs = self.parser.extract_definitions(test_file)
        self.assertGreater(len(defs), 0)

    def test_cpp_parsing(self):
        """Test C++ file parsing."""
        code = """
class Calculator {
public:
    int add(int a, int b) {
        return a + b;
    }
};

int main() {
    return 0;
}
"""
        test_file = self.temp_dir / "calc.cpp"
        test_file.write_text(code)
        
        defs = self.parser.extract_definitions(test_file)
        self.assertGreater(len(defs), 0)

    def test_typescript_parsing(self):
        """Test TypeScript file parsing."""
        code = """
interface User {
    name: string;
    age: number;
}

class UserService {
    getUser(id: number): User {
        return { name: "John", age: 30 };
    }
}

function greet(name: string): void {
    console.log(`Hello, ${name}`);
}
"""
        test_file = self.temp_dir / "user.ts"
        test_file.write_text(code)
        
        defs = self.parser.extract_definitions(test_file)
        self.assertGreater(len(defs), 0)
        names = {d["name"] for d in defs}
        self.assertIn("User", names)
        self.assertIn("UserService", names)

    def test_csharp_parsing(self):
        """Test C# file parsing."""
        code = """
public class Program {
    public static void Main(string[] args) {
        Console.WriteLine("Hello");
    }
    
    private int Add(int a, int b) {
        return a + b;
    }
}
"""
        test_file = self.temp_dir / "Program.cs"
        test_file.write_text(code)
        
        defs = self.parser.extract_definitions(test_file)
        self.assertGreater(len(defs), 0)

    def test_ruby_parsing(self):
        """Test Ruby file parsing."""
        code = """
class Calculator
  def add(a, b)
    a + b
  end

  def subtract(a, b)
    a - b
  end
end

def greet(name)
  puts "Hello, #{name}"
end
"""
        test_file = self.temp_dir / "calc.rb"
        test_file.write_text(code)
        
        defs = self.parser.extract_definitions(test_file)
        self.assertGreater(len(defs), 0)

    def test_swift_parsing(self):
        """Test Swift file parsing."""
        code = """
class Person {
    var name: String
    
    init(name: String) {
        self.name = name
    }
    
    func greet() {
        print("Hello, \\(name)")
    }
}
"""
        test_file = self.temp_dir / "Person.swift"
        test_file.write_text(code)
        
        defs = self.parser.extract_definitions(test_file)
        self.assertGreater(len(defs), 0)

    def test_kotlin_parsing(self):
        """Test Kotlin file parsing."""
        code = """
class Calculator {
    fun add(a: Int, b: Int): Int {
        return a + b
    }
}

fun main() {
    println("Hello")
}
"""
        test_file = self.temp_dir / "Main.kt"
        test_file.write_text(code)
        
        defs = self.parser.extract_definitions(test_file)
        self.assertGreater(len(defs), 0)

    def test_php_parsing(self):
        """Test PHP file parsing."""
        code = """
<?php
class User {
    public function getName() {
        return "John";
    }
}

function greet($name) {
    echo "Hello, " . $name;
}
?>
"""
        test_file = self.temp_dir / "user.php"
        test_file.write_text(code)
        
        defs = self.parser.extract_definitions(test_file)
        self.assertGreater(len(defs), 0)

    def test_unsupported_extension(self):
        """Test that unsupported files return empty."""
        test_file = self.temp_dir / "test.xyz"
        test_file.write_text("some content")
        
        defs = self.parser.extract_definitions(test_file)
        self.assertEqual(len(defs), 0)

    def test_is_supported(self):
        """Test is_supported method."""
        self.assertTrue(self.parser.is_supported(Path("test.py")))
        self.assertTrue(self.parser.is_supported(Path("test.java")))
        self.assertTrue(self.parser.is_supported(Path("test.go")))
        self.assertTrue(self.parser.is_supported(Path("test.rs")))
        self.assertFalse(self.parser.is_supported(Path("test.xyz")))


if __name__ == "__main__":
    unittest.main()
