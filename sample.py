import JsonMerge
import json

# Example usage
if __name__ == "__main__":
    jm = JsonMerge.JSONMERGE()

    # Create a new document with a nested structure
    doc = jm.makeNewDoc({
        "companyName": "TechCorp",
        "address": {
            "street": "123 Tech Lane",
            "city": "Innovate City",
            "state": "CA",
            "zip": "94000"
        },
        "employees": [
            {
                "name": "Alice",
                "employeeID": "E001",
                "department": "Engineering",
                "skills": ["Python", "Machine Learning"]
            },
            {
                "name": "Bob",
                "employeeID": "E002",
                "department": "Design",
                "skills": ["UI/UX", "Adobe Suite"]
            }
        ]
    })

    # Print the initial document in a pretty format
    print("Initial Document:")
    print(json.dumps(doc, indent=2))

    # Update the document with nested changes
    changes = [
        {"address.city": "Silicon Valley"},              # Update city in address
        {"employees.0.skills.1": "Deep Learning"},       # Update Alice's second skill
        {"employees.1.department": "Product Design"},    # Update Bob's department
        {"employees.0.skills.2": "Data Science"}         # Add a new skill to Alice
    ]
    doc = jm.updateDoc(doc, changes)

    # Print the updated document in a pretty format
    print("\nUpdated Document:")
    print(json.dumps(doc, indent=2))

    # Create another document for merging with overlapping and new data
    doc2 = jm.makeNewDoc({
        "companyName": "TechCorp Inc.",
        "address": {
            "street": "456 Innovation Blvd",
            "city": "Techville",
            "state": "CA",
            "zip": "94001"
        },
        "employees": [
            {
                "name": "Alice",
                "employeeID": "E001",
                "department": "R&D",
                "skills": ["Python", "AI", "Quantum Computing"]
            },
            {
                "name": "Charlie",
                "employeeID": "E003",
                "department": "Marketing",
                "skills": ["SEO", "Content Strategy"]
            }
        ]
    })

    # Merge the documents and print the result in a pretty format
    merged = jm.mergeDocReq(doc, doc2)
    print("\nMerged Document:")
    print(json.dumps(merged, indent=2))